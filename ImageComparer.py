import configparser
import datetime
import os
import xml.etree.ElementTree as ET

import cv2
import imagehash
import numpy as np
import pyodbc
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

IMAGE_COMPARER_CONFIG = os.getenv("IMAGE_COMPARER_CONFIG")


class sql_connector:
    """A helper class to handle SQL connections."""

    def __init__(self, config_file):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        self.connection = None
        self.config_file = config_file

    def __enter__(self):
        sql_driver = self.get_driver()

        self.connection = pyodbc.connect(
            driver=sql_driver,
            Server=self.config.get("SQL", "Server"),
            Database=self.config.get("SQL", "Database"),
            User=self.config.get("SQL", "User"),
            Password=self.config.get("SQL", "Key"),
            TrustServerCertificate="yes",
        )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection is not None:
            self.connection.close()

    def get_driver(self):
        """Get the SQL driver."""
        try:
            return pyodbc.drivers()[0]
        except:
            print("Something has gone wrong getting the SQL driver")
            exit()


class image_handler:
    """A helper class to handle SQL image data."""

    def __init__(self, sql_conn, config_handler):
        self.connection = sql_conn.connection
        self.config = config_handler

    def get_std_image(self, project_name, order_number, test_name):
        """Get the standard image for a given project name, order number, and test name."""
        cursor = self.connection.cursor()
        std_run_id = self.config.get("Standard Run ID", project_name)
        query = "SELECT TOP 1 ImageDataId FROM TestData WHERE RunId = ? AND ConnectorOrderNumber = ? AND TestName = ?"
        params = (std_run_id, order_number, test_name)

        image_data_id = cursor.execute(query, params).fetchone()[0]
        query = "SELECT TOP 1 ImageData, TestId, StandardCreatedOnMachineId FROM TestData WHERE ImageDataId = ?"
        params = (image_data_id,)
        data = cursor.execute(query, params).fetchall()[0]
        image_data = data[0]
        std_test_id = data[1]
        std_machine_id = data[2]
        image_data = np.asarray(image_data).tobytes()
        std_img = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        return std_img, std_test_id, std_machine_id

    def get_project_name(self, run_id):
        """Get the project name for a given run id."""
        query = "SELECT TOP 1 DwProjectId FROM TestData WHERE RunId = '{}'".format(
            run_id
        )
        cursor = self.connection.cursor()
        project_id = cursor.execute(query).fetchone()[0]

        query = "SELECT TOP 1 ProjectName FROM DriveWorksProject WHERE DwProjectId = '{}'".format(
            project_id
        )
        project_name = cursor.execute(query).fetchone()[0]
        return project_name

    def get_com_image(self, run_id, order_number, test_name):
        """Get the comparison image for a given run id, order number, and test name."""
        cursor = self.connection.cursor()
        query = "SELECT TOP 1 ImageDataId FROM ViewTestData WHERE RunId = ? AND ConnectorOrderNumber = ? AND TestName = ?"
        params = (run_id, order_number, test_name)

        image_data_id = cursor.execute(query, params).fetchone()[0]
        query = "SELECT TOP 1 ImageData FROM TestData WHERE ImageDataId = ?"
        params = (image_data_id,)
        image_data = cursor.execute(query, params).fetchone()[0]

        std_img = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        return std_img

    def send_masked_image(
        self,
        composite_image,
        std_test_id,
        run_id,
        order_number,
        test_name,
        custom_properties_passed,
        test_duration,
        similarity_score,
    ):
        cursor = self.connection.cursor()
        query = "SELECT TOP 1 StandardCreatedOnMachineId, TestId FROM ViewTestData WHERE RunId = ? AND ConnectorOrderNumber = ? AND TestName = ?"
        params = (run_id, order_number, test_name)
        data = cursor.execute(query, params).fetchall()[0]
        machine_id = data[0]
        test_id = data[1]
        query = "INSERT INTO [{0}].[dbo].[TestResult] ([StandardTestId], [TestId], [RunMachineId], [CustomPropertiesPassed], [ImageDataPassed], [TestDuration], [CompositeImageData], [RecordUpdated], [SimilarityScore]) OUTPUT Inserted.ResultId VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)".format(
            self.config.get("SQL", "Database")
        )

        encoded_composite_image = cv2.imencode(".png", composite_image)[1]
        decoded_composite_image = cv2.imdecode(
            np.frombuffer(encoded_composite_image, np.uint8), cv2.IMREAD_UNCHANGED
        )

        if similarity_score == 1:
            image_data_passed = 1
        else:
            image_data_passed = 0

        # save the decoded image for debugging purposes
        cv2.imwrite("compdecode.png", decoded_composite_image)

        # convert the decoded image to bytes and store it in the database
        decoded_bytes = bytearray(cv2.imencode(".png", decoded_composite_image)[1])
        params = (
            std_test_id,
            test_id,
            machine_id,
            custom_properties_passed,
            image_data_passed,
            test_duration,
            decoded_bytes,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            similarity_score,
        )

        cursor.execute(query, params)
        self.connection.commit()


class image_comparer:
    def compare_images(img1, img2):
        # Resize the images to have the same dimensions
        img1_resized = cv2.resize(
            img1, (img2.shape[1], img2.shape[0]), interpolation=cv2.INTER_AREA
        )
        # Calculate the Mean Squared Error (MSE) between the two blurred images
        mse = np.mean((img1 - img2) ** 2)
        # If the MSE is 0, the images are identical
        if mse == 0:
            composite_image = img1
        # Otherwise, create a grayscale difference image using the absolute difference between the blurred images
        else:
            diff_img = cv2.absdiff(img1, img2)
            gray_img = cv2.cvtColor(diff_img, cv2.COLOR_BGR2GRAY)
            # Threshold the grayscale image to create a binary mask of the differences
            _, mask = cv2.threshold(gray_img, 10, 255, cv2.THRESH_BINARY)
            # Add red pixels to the original image where the mask is white
            composite_image = img2.copy()
            composite_image[mask != 0] = [0, 0, 255]

        # Calculate the perceptual hash of the composite image
        phash_std = imagehash.phash(Image.fromarray(img1), 256)
        phash_comp = imagehash.phash(Image.fromarray(img2), 256)
        hamming_distance = abs(phash_std - phash_comp)

        # Compute the similarity score
        similarity_score = 1 - (hamming_distance / 256.0**2)

        return similarity_score, composite_image


class data_comparer:
    def __init__(self, sql_conn, config_handler):
        self.connection = sql_conn.connection
        self.config = config_handler

    def get_std_test_values(self, project_name, order_number, test_name):
        std_run_id = self.config.get("Standard Run ID", project_name)
        query = "SELECT TOP 1 TestValues FROM TestData WHERE RunId = ? AND ConnectorOrderNumber = ? AND TestName = ?"
        params = (std_run_id, order_number, test_name)
        with self.connection.cursor() as cursor:
            ans = cursor.execute(query, params).fetchone()
            return ans[0]

    def get_com_test_values(self, run_id, order_number, test_name):
        query = "SELECT TOP 1 TestValues FROM ViewTestData WHERE RunId = ? AND ConnectorOrderNumber = ? AND TestName = ?"
        params = (run_id, order_number, test_name)
        with self.connection.cursor() as cursor:
            ans = cursor.execute(query, params).fetchone()
            return ans[0]

    def compare_xml(xml1, xml2):
        """Compare two XML inputs for parity."""
        try:
            root1 = ET.fromstring(xml1)
            root2 = ET.fromstring(xml2)
            return data_comparer.compare_elements(root1, root2)
        except TypeError as e:
            print("No data supplied", e)

    def compare_elements(elem1, elem2):
        """Compare two XML elements for parity."""
        if elem1.tag != elem2.tag:
            return False
        if elem1.text != elem2.text:
            return False
        if elem1.attrib != elem2.attrib:
            return False
        if len(elem1) != len(elem2):
            return False
        for child1, child2 in zip(elem1, elem2):
            if not data_comparer.compare_elements(child1, child2):
                return False
        return True


def run_test(run_id, order_number, test_name):
    """Run the image comparison test for a given run id, order number, and test name."""

    with sql_connector(IMAGE_COMPARER_CONFIG) as sql_conn:
        handler = image_handler(sql_conn, sql_conn.config)
        data_handler = data_comparer(sql_conn, sql_conn.config)
        project_name = handler.get_project_name(run_id)
        std_img, std_test_id, std_machine_id = handler.get_std_image(
            project_name, order_number, test_name=test_name
        )
        com_img = handler.get_com_image(run_id, order_number, test_name)

        similarity_score, composite_image = image_comparer.compare_images(
            std_img, com_img
        )
        print(f"Similarity score: {similarity_score}")

        std_xml = data_handler.get_std_test_values(
            project_name, order_number, test_name
        )
        com_xml = data_handler.get_com_test_values(run_id, order_number, test_name)

        if std_xml == None and com_xml == None:
            print("No mass data related to test")
            xml_passed = True
        else:
            xml_passed = data_comparer.compare_xml(std_xml, com_xml)
            print(f"Data Values Parity: {xml_passed}")

        print(f"Project Name: {project_name}")
        print(f"Connector Order Number: {order_number}")
        print(f"Component: {test_name}")
        cv2.imwrite("test.bmp", composite_image)

        handler.send_masked_image(
            composite_image,
            std_test_id,
            run_id,
            order_number,
            test_name,
            xml_passed,
            1,
            similarity_score,
        )

        return composite_image


""" if __name__ == '__main__':
    runid = '1df6de20-5f05-4b6b-b6d1-3226f851ff34'
    conn_order_no = 2
    test_name = 'Floor Plate.SLDPRT'

    cv2.imwrite('test.png',run_test(runid,
                conn_order_no, test_name))  """

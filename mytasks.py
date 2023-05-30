from celery import Celery

import get_standard_runids
import ImageComparer
import set_new_standard_runid

app = app = Celery(
    "mytasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0"
)

@app.task()
def compare(run_id, order_number, test_name):
    ImageComparer.run_test(
        run_id=run_id, order_number=order_number, test_name=test_name
    )

@app.task()
def get_standard_run_ids():
    return get_standard_runids.execute()

@app.task()
def set_standard_run_id(project_name, new_run_id):
    set_new_standard_runid.execute(project_name, new_run_id)
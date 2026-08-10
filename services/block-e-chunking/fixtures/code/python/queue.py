from celery import Celery
from typing import Dict, Any, Optional
import json

celery_app = Celery('tasks', broker='redis://localhost:6379/1')

class TaskQueue:
    """Manages task queuing with Celery."""
    
    def __init__(self, app: Celery):
        self.app = app
    
    def enqueue(self, task_name: str, args: tuple = (), kwargs: Optional[Dict] = None) -> str:
        """Enqueue a task."""
        result = self.app.send_task(task_name, args=args or (), kwargs=kwargs or {})
        return result.id
    
    def get_status(self, task_id: str) -> str:
        """Get the status of a task."""
        result = self.app.AsyncResult(task_id)
        return result.status
    
    def get_result(self, task_id: str) -> Optional[Any]:
        """Get the result of a completed task."""
        result = self.app.AsyncResult(task_id)
        if result.ready():
            return result.result
        return None

@celery_app.task
def process_document(document_id: str, content: str):
    """Process a document asynchronously."""
    # Simulate processing
    return {"document_id": document_id, "status": "processed", "length": len(content)}

@celery_app.task
def generate_embeddings(chunk_ids: list):
    """Generate embeddings for chunks."""
    # Simulate embedding generation
    return {"chunk_ids": chunk_ids, "status": "embedded"}

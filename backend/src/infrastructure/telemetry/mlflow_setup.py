"""
MLflow Setup
Configures MLflow tracking and LangChain autologging.
"""
from __future__ import annotations

import structlog

from ...application.config import get_settings

logger = structlog.get_logger(__name__)


def setup_mlflow(service_name: str) -> None:
    """
    Initialize MLflow tracing and enable LangChain autologging.
    """
    settings = get_settings()

    if not settings.mlflow_enabled:
        logger.info("mlflow_disabled")
        return

    try:
        import mlflow
        
        # Set the Tracking URI
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        
        # Set the Experiment Name
        mlflow.set_experiment(settings.mlflow_experiment_name)
        
        # Enable LangChain Autologging
        # We wrap it in a try-except to avoid crashing if LangChain isn't installed
        # or if the specific module is missing.
        try:
            import langchain
            mlflow.langchain.autolog()
            logger.info("mlflow_langchain_autolog_enabled")
        except ImportError:
            logger.warning("mlflow_langchain_autolog_failed_langchain_not_installed")
            
        logger.info(
            "mlflow_initialized", 
            tracking_uri=settings.mlflow_tracking_uri, 
            experiment_name=settings.mlflow_experiment_name
        )
    except Exception as e:
        logger.error("mlflow_initialization_failed", error=str(e))

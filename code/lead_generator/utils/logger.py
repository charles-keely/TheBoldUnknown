import logging
import sys
from rich.logging import RichHandler

def setup_logger(name: str = "lead_gen", level: str = "INFO") -> logging.Logger:
    """
    Sets up a logger with RichHandler for pretty console output
    and a FileHandler for detailed logging.
    """
    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers if setup_logger is called multiple times
    if logger.handlers:
        return logger
        
    logger.setLevel(level)

    # Console Handler (Rich)
    console_handler = RichHandler(rich_tracebacks=True, markup=True)
    console_handler.setLevel(level)
    console_format = logging.Formatter("%(message)s", datefmt="[%X]")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File Handler
    file_handler = logging.FileHandler("app.log")
    file_handler.setLevel(logging.DEBUG)  # Capture everything in file
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()

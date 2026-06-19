"""Custom exception classes for the image sensor processing system."""


class ImageSensorError(Exception):
    """Base exception for image sensor processing."""
    pass


class ProcessingError(ImageSensorError):
    """Processing pipeline error."""
    pass

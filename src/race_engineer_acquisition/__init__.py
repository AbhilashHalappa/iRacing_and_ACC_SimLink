"""High-priority ACC telemetry acquisition foundation."""

from .models import PhysicsSnapshot, RawPhysicsRead
from .health import AcquisitionHealth, AcquisitionHealthSnapshot
from .ring_buffer import AcquisitionRingBuffer
from .fanout import BoundedConsumerQueue, FanOutDispatcher, ConsumerQueueMetrics, FanOutMetrics
from .acc_windows import WindowsACCPhysicsSource
from .recorder import PhysicsRecorderWorker, RawPhysicsRecordingWriter, recover_recording
from .static_recording import StaticRecorderWorker, RawStaticRecordingWriter, recover_static_recording
from .supervisor import (
    AcquisitionStream, AcquisitionSupervisor, AcquisitionStartupError,
    ACCAcquisitionRuntime, create_acc_acquisition_runtime,
)

__all__ = [
    "AcquisitionHealth",
    "AcquisitionHealthSnapshot",
    "PhysicsSnapshot",
    "RawPhysicsRead",
    "AcquisitionRingBuffer",
    "BoundedConsumerQueue",
    "FanOutDispatcher",
    "ConsumerQueueMetrics",
    "FanOutMetrics",
    "PhysicsRecorderWorker",
    "RawPhysicsRecordingWriter",
    "recover_recording",
    "StaticRecorderWorker",
    "RawStaticRecordingWriter",
    "recover_static_recording",
    "AcquisitionStream",
    "AcquisitionSupervisor",
    "AcquisitionStartupError",
    "ACCAcquisitionRuntime",
    "create_acc_acquisition_runtime",
]

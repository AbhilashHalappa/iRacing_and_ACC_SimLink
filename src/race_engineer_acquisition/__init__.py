"""High-priority ACC telemetry acquisition foundation."""

from .models import PhysicsSnapshot, RawPhysicsRead
from .physics_decoder import DecodedPhysics, decode_physics, WHEEL_ORDER
from .physics_consumer import PhysicsDecodeConsumer, PhysicsConsumerSnapshot
from .graphics_decoder import DecodedGraphics, decode_graphics
from .graphics_consumer import GraphicsDecodeConsumer, GraphicsConsumerSnapshot
from .health import AcquisitionHealth, AcquisitionHealthSnapshot
from .fuel_engineer import FuelEngineerSnapshot, build_fuel_engineer_snapshot
from .fuel_strategy import FuelStrategyAssessment, assess_fuel_strategy
from .service import RaceEngineerService
from .lap_events import (
    CompletedLapEventObserver,
    LapEventCandidate,
    LapProgressReconciliation,
    reconcile_lap_progress,
)
from .decoded_events import (
    DecodedDomainEvent,
    EventDeliveryBatch,
    DecodedEventSubscription,
    DecodedEventPublisher,
)
from .decoded_distribution import (
    DecodedTelemetryBroker,
    DecodedSnapshotEnvelope,
    LatestSnapshotSubscription,
)
from .engineering_snapshot import (
    RaceEngineerSnapshotAggregator,
    RaceEngineerTelemetrySnapshot,
    TelemetryStreamView,
    RawStreamHealthView,
)
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
    "FuelEngineerSnapshot",
    "build_fuel_engineer_snapshot",
    "FuelStrategyAssessment",
    "assess_fuel_strategy",
    "RaceEngineerService",
    "CompletedLapEventObserver",
    "LapEventCandidate",
    "LapProgressReconciliation",
    "reconcile_lap_progress",
    "DecodedDomainEvent",
    "EventDeliveryBatch",
    "DecodedEventSubscription",
    "DecodedEventPublisher",
    "DecodedTelemetryBroker",
    "DecodedSnapshotEnvelope",
    "LatestSnapshotSubscription",
    "RaceEngineerSnapshotAggregator",
    "RaceEngineerTelemetrySnapshot",
    "TelemetryStreamView",
    "RawStreamHealthView",
    "PhysicsSnapshot",
    "DecodedPhysics",
    "PhysicsDecodeConsumer",
    "PhysicsConsumerSnapshot",
    "DecodedGraphics",
    "decode_graphics",
    "GraphicsDecodeConsumer",
    "GraphicsConsumerSnapshot",
    "decode_physics",
    "WHEEL_ORDER",
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

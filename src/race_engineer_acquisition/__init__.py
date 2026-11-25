"""ACC telemetry acquisition and live Overview runtime primitives."""

from .models import PhysicsSnapshot, RawPhysicsRead
from .physics_decoder import DecodedPhysics, decode_physics, WHEEL_ORDER
from .physics_consumer import PhysicsDecodeConsumer, PhysicsConsumerSnapshot
from .graphics_decoder import DecodedGraphics, decode_graphics
from .graphics_consumer import GraphicsDecodeConsumer, GraphicsConsumerSnapshot
from .static_consumer import StaticDecodeConsumer, StaticConsumerSnapshot
from .health import AcquisitionHealth, AcquisitionHealthSnapshot
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
from .acc_windows import WindowsACCPhysicsSource
from .supervisor import (
    AcquisitionStream,
    AcquisitionSupervisor,
    AcquisitionStartupError,
    ACCAcquisitionRuntime,
    create_acc_acquisition_runtime,
)

__all__ = [
    "AcquisitionHealth", "AcquisitionHealthSnapshot",
    "CompletedLapEventObserver", "LapEventCandidate",
    "LapProgressReconciliation", "reconcile_lap_progress",
    "DecodedDomainEvent", "EventDeliveryBatch",
    "DecodedEventSubscription", "DecodedEventPublisher",
    "DecodedTelemetryBroker", "DecodedSnapshotEnvelope",
    "LatestSnapshotSubscription", "RaceEngineerSnapshotAggregator",
    "RaceEngineerTelemetrySnapshot", "TelemetryStreamView",
    "RawStreamHealthView", "PhysicsSnapshot", "RawPhysicsRead",
    "DecodedPhysics", "decode_physics", "WHEEL_ORDER",
    "PhysicsDecodeConsumer", "PhysicsConsumerSnapshot",
    "DecodedGraphics", "decode_graphics", "GraphicsDecodeConsumer",
    "GraphicsConsumerSnapshot", "StaticDecodeConsumer",
    "StaticConsumerSnapshot", "AcquisitionRingBuffer",
    "WindowsACCPhysicsSource", "AcquisitionStream",
    "AcquisitionSupervisor", "AcquisitionStartupError",
    "ACCAcquisitionRuntime", "create_acc_acquisition_runtime",
]

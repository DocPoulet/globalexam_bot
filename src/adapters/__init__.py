from .ordering import OrderingDragDropAdapter
from .qcm import QcmAdapter
from .select import SelectAdapter
from .text_input import TextInputAdapter
from .unknown import UnknownAdapter

ADAPTERS = [
    OrderingDragDropAdapter,
    QcmAdapter,
    SelectAdapter,
    TextInputAdapter,
    UnknownAdapter,
]

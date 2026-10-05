from .ordering import OrderingAdapter
from .qcm import QcmAdapter
from .span_choice import SpanChoiceAdapter
from .button_choice import ButtonChoiceAdapter
from .select import SelectAdapter
from .text_input import TextInputAdapter
from .unknown import UnknownAdapter

ADAPTERS = [
    OrderingAdapter,
    QcmAdapter,
    SpanChoiceAdapter,
    ButtonChoiceAdapter,
    SelectAdapter,
    TextInputAdapter,
    UnknownAdapter,
]

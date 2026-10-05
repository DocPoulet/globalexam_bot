from .ordering import OrderingAdapter
from .qcm import QcmAdapter
from .button_choice import ButtonChoiceAdapter
from .select import SelectAdapter
from .text_input import TextInputAdapter
from .unknown import UnknownAdapter

ADAPTERS = [
    OrderingAdapter,
    QcmAdapter,
    ButtonChoiceAdapter,
    SelectAdapter,
    TextInputAdapter,
    UnknownAdapter,
]

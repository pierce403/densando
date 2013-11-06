from google.appengine.api import search

from models import Test

search.Document(
    fields = [
        search.AtomField( name="group", value=)
    ]
)

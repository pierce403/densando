
from google.appengine.ext import ndb

## Look at all these glamorous MODELS
class Test( ndb.Model ):
    id = ndb.StringProperty( indexed=True )
    title = ndb.StringProperty( indexed=True )
    description = ndb.TextProperty( indexed=False )
    group = ndb.StringProperty( indexed=True )
    created = ndb.DateTimeProperty( )
    modified = ndb.DateTimeProperty( )
    author_id = ndb.StringProperty( indexed=True )
    times_taken = ndb.IntegerProperty( indexed=False )
    total_score = ndb.IntegerProperty( indexed=False )
    num_marked = ndb.IntegerProperty( indexed=False )
    open = ndb.BooleanProperty( indexed=True )
    average_rating = ndb.FloatProperty( indexed=True )
    level = ndb.IntegerProperty( indexed=True )

class Entity( ndb.Model ):
    # About the user
    user = ndb.UserProperty( indexed=True )
    id = ndb.StringProperty( indexed=True )
    display_name = ndb.StringProperty( indexed=True )
    created = ndb.DateTimeProperty( )
    modified = ndb.DateTimeProperty( )
    bio = ndb.TextProperty( indexed=False )
    test_groups = ndb.StringProperty( indexed=True, repeated=True )

class Mark( ndb.Model ):
    marker_entity = ndb.StructuredProperty( Entity, indexed=True )
    taker_entity = ndb.StructuredProperty( Entity, indexed=True )
    test = ndb.StructuredProperty( Test, indexed=True )
    response = ndb.StringProperty( indexed=False )
    comment = ndb.StringProperty( indexed=False )
    complete = ndb.BooleanProperty( indexed=True )
    mark = ndb.IntegerProperty( indexed=False )
    created = ndb.DateTimeProperty( )
    modified = ndb.DateTimeProperty( )
    id = ndb.StringProperty( indexed=True )
    rating = ndb.IntegerProperty( indexed=True )
    rated = ndb.BooleanProperty( indexed=True )

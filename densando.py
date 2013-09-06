# Imports from the Internet's greatest language
import webapp2
import datetime
import os
import logging
import hashlib
# Imports from GAE
from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import ndb

## Constants
template_dir = 'templates/'

## Views to Render

class MainPage(webapp2.RequestHandler):
    logger = logging.getLogger("MainPage")
    
    def get(self):
        template_values = get_template_values( self )
        
        template_values['recent_tests'] = get_most_recent_tests(5)
        print template_values['recent_tests']
        
        path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'main.html' ) )
        self.response.out.write( template.render( path, template_values ))
        return
        
class LoginHandler( webapp2.RequestHandler ):
    logger = logging.getLogger("LoginHandler")
    
    def get(self):
        template_values = get_template_values( self )
        user = users.get_current_user()
        if user:
            self.logger.info(user)
            entity_query = Entity.query( Entity.id == user.user_id() ).fetch()
            if len(entity_query) > 0:
                entity = entity_query[0]
                if not entity.display_name:
                    display_name = self.request.get( 'display_name' )
                else:
                    display_name = entity.display_name
                self.logger.info( "display name= %s", display_name )
                if display_name:
                    entity.display_name = display_name        
                    entity.modified = datetime.datetime.now()
                    entity.put()
                else:
                    path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'register.html' ) )
                    self.response.out.write( template.render( path, template_values ))
                    return
                self.redirect('/')
            else:
                # the entity for this user hasn't been created yet
                self.logger.info( user )
                entity = Entity(
                    user = user,
                    id = user.user_id(),
                    created = datetime.datetime.now(),
                )
                self.logger.info( entity )
                entity.put()
                path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'register.html' ) )
                self.response.out.write( template.render( path, template_values ))
        else:
            print user
            self.redirect( users.create_login_url( '/login' ) )
        return

class CreateAlterTest( webapp2.RequestHandler ):
    
    def get(self, in_test_id=None):
        template_values = get_template_values( self )
        user = users.get_current_user()
        try:
            entity_query = Entity.query( Entity.id == user.user_id() ).fetch()
        except:
            self.redirect('/login')
        else:
            if len (entity_query)>0:
                entity = entity_query[0]
                test_query = Test.query( ancestor = ndb.Key('Entity', user.user_id() ) )
                logging.debug("TEST QUERY: %s, ENTITY QUERY: %s", test_query, entity_query )
                if len(test_query.fetch()) > 0:
                    logging.debug("TEST QUERY: %s, LOOK FOR: %s", test_query, in_test_id )
                    if in_test_id:
                        in_query = test_query.filter( Test.id == in_test_id ).fetch(1)
                        logging.debug("Fetch: %s", in_query )
                        # The test exists
                        template_values = add_test_to_template( template_values, in_query[0] )
                
                path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'create.html' ) )
                self.response.out.write( template.render( path, template_values ))
        return

        
    def post(self):
        user = users.get_current_user()
        test_query = Test.query( ancestor = ndb.Key('Entity', user.user_id()) )
        test_query = test_query.filter( Test.id == self.request.get( 'title' ) ).fetch()
        logging.debug("TEST QUERY: %s", test_query)
        
        if len(test_query) > 0:
            test = test_query[0]
            test.modified = datetime.datetime.now()
        else:
            test = Test( parent = ndb.Key('Entity', user.user_id() ) )
            test.created = datetime.datetime.now()
            
        test.author_id = user.user_id()
        test.title = self.request.get( 'title' )
        test.description = self.request.get( 'description' )
        test.group = self.request.get( 'group' )   
        test.id = str( test.put().id() )
        test.put()
        
        logging.debug( "Test: %s", test )
        self.redirect('/t/%s' % test.id )
        return
 

class UserProfile( webapp2.RequestHandler ):
    
    def get(self, profile_to_get=None):
        template_values = get_template_values( self )
        user = users.get_current_user()
        if user:
            
            if not profile_to_get or profile_to_get ==  user.user_id():
                logging.info("Fetch this humanoid's profile! (%s)", user.user_id() )
                entity_query = Entity.query( Entity.id == user.user_id() ).fetch() 
            else:
                logging.info("Fetch this humanoid's profile! (%s)", user.user_id() )
                template_values = add_entity_to_template(template_values, user )
                logging.info("Fetch profile for other humanoid! (%s)", profile_to_get )
                entity_query = Entity.query( Entity.id == profile_to_get ).fetch()
            
            entity = entity_query[0]
            test_query = Test.query( ancestor = ndb.Key('Entity', entity.id ) ).fetch(1)
            
            if len(entity_query) > 0:
                template_values = add_entity_to_template(template_values, entity )
                path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'profile.html' ) )
                self.response.out.write( template.render( path, template_values ))
                return
        else:
            self.redirect('/')
        logging.warning("OUT OF BOUNDS (%s)", profile_to_get )
        self.redirect('/')
        return
        
        
class TestView( webapp2.RequestHandler ):
    
    def get(self, test_to_get=None):
        template_values = get_template_values( self )
        user = users.get_current_user()
        if user:
            entity = Entity.query( Entity.id == user.user_id() ).fetch()[0]
            template_values = add_entity_to_template(template_values, entity )
        if not test_to_get:
            logging.info("No test was provided for lookup")
            self.redirect('/u')
        else:
            test_query = Test.query( Test.id == test_to_get).fetch(1)
            template_values = add_test_to_template( template_values, test_query[0] )
            path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'test_detail.html') )
            self.response.out.write( template.render( path, template_values) )            
        return
            
## Look at all these glamorous MODELS
        
class Test( ndb.Model ):
    id = ndb.StringProperty( indexed=True )
    title = ndb.StringProperty( indexed=True )
    description = ndb.TextProperty( indexed=True )
    group = ndb.StringProperty( indexed=False )
    created = ndb.DateTimeProperty( )
    modified = ndb.DateTimeProperty( )
    author_id = ndb.StringProperty( indexed=True )

class Entity( ndb.Model ):
    # About the user
    user = ndb.UserProperty( indexed=True )
    id = ndb.StringProperty( indexed=True )
    display_name = ndb.StringProperty( indexed=True )
    created = ndb.DateTimeProperty( )
    modified = ndb.DateTimeProperty( )
    bio = ndb.TextProperty( indexed=False )

class Mark( ndb.Model ):
    """Controls lots of things
    
    When a User/Entity starts a Test, a Mark is created with:   ## In-Progress Stage
        - parent = user's Entity.Key
        - marker_entity = None
        - test = associated Test
        - response = None
        - complete = False
        - mark = None
        - creation/timestamp of Now
        
    When a User submits their answer:                           ## Pending Stage
        - response = the answer
        - marker_entity = Test.group
        
    When a marker gives a mark:                                 ## Completed Stage
        - mark = the numeric mark for the user's response
        - complete = True
    
    """
    marker_entity = ndb.StructuredProperty( Entity, indexed=False )
    test = ndb.StructuredProperty( Test, indexed=False )
    response = ndb.StringProperty( indexed=False )
    complete = ndb.BooleanProperty( indexed=False )
    mark = ndb.IntegerProperty( indexed=False )
    created = ndb.DateTimeProperty( )
    modified = ndb.DateTimeProperty( )

## Helper Functions

def add_entity_to_template( template_values, in_entity ):
    """Combines Entity object properties into template_values"""
    logging.debug( in_entity )
    template_values['name'] = in_entity.display_name
    template_values['id'] = in_entity.id
    template_values['created'] = in_entity.created
    template_values['modified'] = in_entity.modified
    template_values['bio'] = in_entity.bio
    ## These need to be computed
    # template_values['completed'] = get_completed_tests( in_entity )
    # template_values['pending'] = get_pending_tests( in_entity )
    # template_values['in_prograss'] = get_in_progess_tests( in_entity )
    template_values['my_tests'] = get_created_tests( in_entity )
    
    return template_values
    
def add_test_to_template( template_values, in_test ):
    """Combines Test object properties into template_values"""
    logging.info( in_test )
    template_values['test_id'] = in_test.id
    template_values['title'] = in_test.title
    template_values['description'] = in_test.description
    template_values['group'] = in_test.group
    template_values['test_created'] = in_test.created
    template_values['test_modified'] = in_test.modified
    template_values['author_id'] = in_test.author_id

    return template_values
    
def get_completed_tests( entity ):
    pass    
    
def get_pending_tests( entity ):
    pass
    
def get_in_progess_tests( entity ):
    pass    

def get_created_tests( entity, num=None ):
    """Retrieves the tests that have been created by entity"""
    test_query = Test.query( ancestor = ndb.Key('Entity', entity.id) )
    if not num:
        return test_query.fetch()
    else:
        return test_query.fetch( num )
        
def get_most_recent_tests( num=None ):
    """Retrieves the num most recent test"""
    test_query = Test.query().order( -Test.created )
    if len(test_query.fetch()) > 0:
        if not num:
            return test_query.fetch()
        else:
            return test_query.fetch( num )
    else:
        return []

def get_template_values( self ):
    """Constructs and returns a dict of common values needed by all or nearly all templates"""
    user = users.get_current_user()
    
    template_values= {
        'date'      : datetime.datetime.now(),
        'nav_urls'  : get_navigation_urls( self, user ),
    }
    if user:
        template_values['user'] = user
        template_values['user_id'] = user.user_id()
    else:
        template_values['user'] = False
    return template_values

def get_navigation_urls( self, user ):
    """Constructs and returns a dict of common urls used for navigation"""
    navigation_urls = {
        'home'  : '/',
        'create_test': '/c',
        'profile': '/u'
    }
    if user:
        navigation_urls['logout'] = users.create_logout_url( '/' )
    else:
        navigation_urls['login'] = users.create_login_url( '/login' )
    return navigation_urls

    
    
# Run Runaway!
app = webapp2.WSGIApplication( [
    ( '/'  , MainPage ),
    ( '/login', LoginHandler ),
    ( '/c/([^/]+)', CreateAlterTest ),
    ( '/c', CreateAlterTest ),
    ( '/u/([^/]+)', UserProfile ),
    ( '/u', UserProfile ),
    ( '/t/([^/]+)', TestView ),
    ( '/t', TestView ),
], debug = True)

def main():
    run_wsgi_app(app)

if __name__ == '__main__':
    main()
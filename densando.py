# Imports from the Internet's greatest language
import webapp2
import datetime
import os
import logging
import hashlib
import urlparse
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
                    entity.bio = self.request.get( 'bio' )
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
                logging.info("Fetch this humanoid's info! (%s)", user.user_id() )
                #template_values = add_entity_to_template(template_values, user )
                logging.info("Fetch profile for other humanoid! (%s)", profile_to_get )
                entity_query = Entity.query( Entity.id == profile_to_get ).fetch()
            
            entity = entity_query[0]
            #test_query = Test.query( ancestor = ndb.Key('Entity', entity.id ) ).fetch(1)
            
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

        if not test_to_get:
            logging.info("No test was provided for lookup")
            self.redirect('/')
            return
        else:
            try:
                test = Test.query( Test.id == test_to_get).fetch(1)[0]
            except IndexError:
                logging.info("Invalid Test ID")
                self.redirect('/')
            else:
                if user:
                    template_values = add_entity_to_template( template_values, Entity.query( Entity.id == user.user_id() ).fetch(1)[0] )
                    try:
                        mark_query = Mark.query( ancestor = ndb.Key("Entity", user.user_id() ) )
                        mark = mark_query.filter( Mark.test.id == test.id ).fetch(1)[0]
                        template_values = add_mark_to_template( template_values, mark )
                        if (datetime.datetime.now() - mark.modified) < datetime.timedelta(minutes=10):
                            template_values['locked'] = True
                    except IndexError:
                        logging.info( "No mark found" )
                        template_values = add_test_to_template( template_values, test )
                    finally:    
                        if test.author_id == user.user_id():
                            template_values['is_test_marker'] = True
                            test_marker = Entity.query( Entity.id == user.user_id() ).fetch()[0]
                            template_values['to_be_marked'] = get_to_be_marked( test_marker, test )
                            template_values['name'] = test_marker.display_name
                            template_values['current_user'] = user.user_id()
                            logging.info( "test.author_id == user.user_id()" )
                
                else: 
                    template_values['locked'] = True
                    logging.warning("User not found!")
                    template_values = add_test_to_template( template_values, test )
                    
                    
            finally:
            
                path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'test_detail.html') )
                self.response.out.write( template.render( path, template_values) )            
        return
        
    def post(self):
        test_id = self.request.get( 'test_id' )
        author_id = self.request.get( 'author_id' )
        user = users.get_current_user()
        if user:
            test = Test.query( Test.id == test_id ).fetch()[0]
            mark_query = Mark.query( ancestor = ndb.Key("Entity", user.user_id() ) )
            mark_query = mark_query.filter( Mark.test.id == test.id )
            try:
                this_mark = mark_query.fetch()[0]
            except IndexError:
                this_mark = Mark( parent = ndb.Key("Entity", user.user_id() ) )
                this_mark.test = test
                this_mark.created = datetime.datetime.now()
                this_mark.mark = None
                
            this_mark.response = self.request.get( 'response' )
            this_mark.complete = False
            this_mark.modified = datetime.datetime.now()
            this_mark.id = test_id + user.user_id()
            this_mark.marker_entity = Entity.query( Entity.id == author_id ).fetch()[0]
            this_mark.taker_entity = Entity.query( Entity.id == user.user_id() ).fetch()[0]
            this_mark.put()

        self.redirect( '/t/%s' % test_id )
        return
        
        
class MarkView( webapp2.RequestHandler ):
    
    # def get(self, mark_or_user=None):
    
        # template_values = get_template_values( self )
        # user = users.get_current_user()
    
        # if mark_or_user:
            # try:
                # entity = Entity.query( Entity.id == mark_or_user ).fetch(1)[0] 
                # template_values = add_entity_to_template( template_values, entity )
                # template_values['current_user'] = user.user_id()
            # except IndexError:
                # try:
                    # mark = Mark.query( Mark.id == mark_or_user ).fetch(1)[0]
                    # template_values = add_mark_to_template( template_values, mark )
                # except:
                    # ## if it's not a mark or an entityid, maybe it's half?
                    # mark = Mark.query( Mark.id == mark_or_user + user.user_id() ).fetch(1)[0]           
                    # template_values = add_mark_to_template( template_values, mark )
                # finally:
                    # path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'mark_detail.html') )
                    # self.response.out.write( template.render( path, template_values) )
                    
            # else:
                # # Parameter was a user.id, so load the master page
                # path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'marks.html') )
                # self.response.out.write( template.render( path, template_values) )
        # else:
            # try:
                # entity = Entity.query( Entity.id == user.user_id() ).fetch(1)[0] 
                # template_values = add_entity_to_template( template_values, entity )
                # template_values['current_user'] = user.user_id()
            # except:
                # raise
            # else:
                # path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'marks.html') )
                # self.response.out.write( template.render( path, template_values) )
        # return       
        
    def post( self, in_test_id ):
        path = urlparse.urlsplit(self.request.referrer).path
        user = users.get_current_user()
        author_id = self.request.get("author_id")
        test_id = self.request.get("test_id")
        mark_id = self.request.get("mark_id")
        comment = self.request.get("comment")
        response = self.request.get("response")
        mark = self.request.get("mark")
        
        author_entity = Entity.query( Entity.id == author_id ).fetch(1)[0]
        user_entity = Entity.query( Entity.id == user.user_id() ).fetch(1)[0]
        test_entity = Test.query( Test.id == test_id ).fetch(1)[0]        
        mark_entity = Mark.query( ancestor = ndb.Key("Entity", mark_id) )
        mark_entity = mark_entity.filter( Mark.test.id == test_id ).fetch(1)[0]
        # print "***********************"
        # print path
        # print user
        # print author_id
        # print test_id
        # print testee_id
        # print comment
        # print response
        # print mark
        # print author_entity
        # print user_entity
        # print test_entity
        # print "***********************"
        
        # logger = logging.getLogger("TestLogger")
        # print Mark.query( Mark.test.id == test_id ).fetch()
        # print testee_id
        
        
        mark_entity.marker_entity = author_entity
        mark_entity.test = test_entity
        mark_entity.response = response
        mark_entity.comment = comment
        mark_entity.mark = int(mark)
        mark_entity.modified = datetime.datetime.now()
        mark_entity.complete = True
        mark_entity.put()
        self.redirect( path )
        return
        
        
        
            
## Look at all these glamorous MODELS
        
class Test( ndb.Model ):
    id = ndb.StringProperty( indexed=True )
    title = ndb.StringProperty( indexed=True )
    description = ndb.TextProperty( indexed=True )
    group = ndb.StringProperty( indexed=False    )
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

## Helper Functions

def add_mark_to_template( template_values, in_mark ):
    """Combines Mark object properties into template_values"""
    logging.info(in_mark)
    template_values = add_entity_to_template( template_values, in_mark.marker_entity )
    template_values = add_test_to_template( template_values, in_mark.test )
    template_values['complete'] = in_mark.complete
    template_values['response'] = in_mark.response
    template_values['comment'] = in_mark.comment
    template_values['mark'] = in_mark.mark
    template_values['mark_id'] = in_mark.id
    template_values['mark_created'] = in_mark.created
    template_values['mark_modified'] = in_mark.modified
    return template_values
    
def add_entity_to_template( template_values, in_entity ):
    """Combines Entity object properties into template_values"""
    logging.debug( in_entity )
    template_values['name'] = in_entity.display_name
    template_values['id'] = in_entity.id
    template_values['created'] = in_entity.created
    template_values['modified'] = in_entity.modified
    template_values['bio'] = in_entity.bio
    ## Lists of Tests
    template_values['completed'] = get_completed_tests( in_entity )
    template_values['completed_cnt'] = len( template_values['completed'] )
    template_values['in_progress'] = get_in_progess_tests( in_entity )
    template_values['in_progress_cnt'] = len( template_values['in_progress'] )
    template_values['my_tests'] = get_created_tests( in_entity )
    template_values['my_tests_cnt'] = len( template_values['my_tests'] )
    ## Lists of Marks
    template_values['to_be_marked'] = get_to_be_marked( in_entity )
    template_values['to_be_marked_cnt'] = len( template_values['to_be_marked'] ) 
    
    return template_values
    
def add_test_to_template( template_values, in_test ):
    """Combines Test object properties into template_values"""
    #logging.info( in_test )
    template_values['test_id'] = in_test.id
    template_values['title'] = in_test.title
    template_values['description'] = in_test.description
    template_values['group'] = in_test.group
    template_values['test_created'] = in_test.created
    template_values['test_modified'] = in_test.modified
    template_values['author_id'] = in_test.author_id

    return template_values

def get_completed_tests( entity, num=None ):
    mark_query = Mark.query( ancestor = ndb.Key('Entity', entity.id) )
    mark_query = mark_query.filter( Mark.complete == True )
    if not num:
        return [mark.test for mark in mark_query.fetch()]
    else:
        return mark_query.fetch( num )    
    
def get_in_progess_tests( entity, num=None ):
    mark_query = Mark.query( ancestor = ndb.Key('Entity', entity.id) )
    mark_query = mark_query.filter( Mark.complete == False )
    if not num:
        return [mark.test for mark in mark_query.fetch()]
    else:
        return mark_query.fetch( num )  

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

def get_to_be_marked( entity, test=None, num=None ):
    """Retrieves the responses from other entities that need to have marks assigned for tests created by this entity"""
    mark_query = Mark.query( Mark.marker_entity.id == entity.id )
    mark_query = mark_query.filter( Mark.complete == False )
    if test:
        mark_query = mark_query.filter( Mark.test.id == test.id ) 
    
    if not num:
        return mark_query.fetch()
    else:
        return mark_query.fetch( num )
        
def get_marked( entity, num=None ):
    """Retrieves the responses from other entitis that need to have marks assigned for tests created by this entity"""
    mark_query = Mark.query( Mark.marker_entity.id == entity.id )
    mark_query = mark_query.filter( Mark.complete == True )
    if not num:
        return mark_query.fetch()
    else:
        return mark_query.fetch( num )
        
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
    ( '/m/([^/]+)', MarkView ),
    ( '/m', MarkView ),
], debug = True)

def main():
    run_wsgi_app(app)

if __name__ == '__main__':
    main()
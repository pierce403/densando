from __future__ import division # This forces divisions to return floats, which is the default behaviour in Python 3, but not Python 2
import webapp2
import datetime
import os
import logging
import urlparse
import math
import time
import re
import json
import itertools
# for encoding urls and generating md5 hashes
import hashlib

## Imports from GAE
from google.appengine.ext.webapp import template
from google.appengine.api import users, memcache, mail
from google.appengine.ext import ndb
from google.appengine.datastore.datastore_query import Cursor

## Constants
template_dir = 'templates/'
default_groups = ['python', 'javascript', 'sql', 'json']

## Views to Render
class MainPage(webapp2.RequestHandler):
    logger = logging.getLogger("MainPage")
    
    def get(self):
        template_values = get_template_values( self )
        start_cursor = Cursor(urlsafe=self.request.get('next'))
        # only return open tests with open=True
        template_values['recent_tests'] = get_tests( num=5, start_cursor=start_cursor, open=True )
        path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'main.html' ) )
        self.response.out.write( template.render( path, template_values ))
        return
        
class OpenCloseTest( webapp2.RequestHandler ):
    logger = logging.getLogger("OpenCloseTest")

    def get(self, test_id, open):
        open = True if open=="t" else False
        user = users.get_current_user()
        test_query = Test.query( ancestor = ndb.Key("Entity", user.user_id()) ).filter( Test.id == test_id )
        test_entity = test_query.fetch(1)[0]
        if open and not test_entity.open:
            test_entity.open = True
            test_entity.put()
        if not open and test_entity.open:
            test_entity.open = False
            test_entity.put()

        self.redirect("/u")
       
class RegistrationHandler( webapp2.RequestHandler ):
    def get(self):
        template_values = get_template_values( self )
        user = users.get_current_user()
        if user:
            path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'register.html' ) )
            self.response.out.write( template.render( path, template_values ))
        else:
            self.redirect('/')
        return

    def post(self):
        template_values = get_template_values( self )
        user = users.get_current_user()
        try:
            entity_query = Entity.query( Entity.id == user.user_id() ).fetch()
            entity = entity_query[0]
        except IndexError:
            # This user must not exist yet, so create one
            entity = Entity(
                user = user,
                id = user.user_id(),
                created = datetime.datetime.now(),
                test_groups = [],
            )

        posted_name = self.request.get( 'display_name' ) if len(self.request.get( 'display_name' )) > 0 else self.request.get( 'user_name' )

        # Show an error if the name isn't formatted properly.
        if re.match('^[a-z0-9]{3,16}$', posted_name) is None:
            template_values['error'] = "Usernames must be 16 or fewer alphanumeric characters [a-z0-9]."
            path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'register.html' ) )
            self.response.out.write( template.render( path, template_values ))
            return

        users_with_name = Entity.query( Entity.display_name == posted_name ).count()
        if users_with_name == 0 or entity.display_name == posted_name:
            # Update values
            entity.display_name = posted_name if posted_name else entity.display_name
            entity.bio = self.request.get( 'bio' ) if len(self.request.get( 'bio' )) > 0 else "I am mysterious."
            # Save and visit
            entity.put()
            time.sleep(0.1)         # The user doesn't exist for a short period of time after put()
            self.redirect('/u/%s' % entity.display_name )
        else:
            template_values['error'] = "That username is in use.  Please choose again."
            path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'register.html' ) )
            self.response.out.write( template.render( path, template_values ))
        return

class LoginHandler( webapp2.RequestHandler ):
    logger = logging.getLogger("LoginHandler")
    
    def get(self):
        template_values = get_template_values( self )
        user = users.get_current_user()
        try:
            entity = Entity.query( Entity.id == user.user_id() ).fetch()[0]
            if not entity.display_name:
                path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'register.html' ) )
                self.response.out.write( template.render( path, template_values ))
            else:
                self.redirect('/u')
        except IndexError:
            path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'register.html' ) )
            self.response.out.write( template.render( path, template_values ))
        return




class CreateAlterTest( webapp2.RequestHandler ):
    logger = logging.getLogger("CreateAlterTest")
    
    def get(self, in_test_id=None):
        template_values = get_template_values( self )
        user = users.get_current_user()
        try:
            entity = Entity.query( Entity.id == user.user_id() ).fetch()[0]
            if not entity.display_name: # It's only slightly possible to have a user with no display_name
                self.redirect('/login')
        except:
            self.redirect('/login')
        else:
            test_query = Test.query( ancestor = ndb.Key('Entity', user.user_id() ) )
            if len(test_query.fetch()) > 0:
                if in_test_id:
                    in_query = test_query.filter( Test.id == in_test_id ).fetch(1)
                    try: # The test exists
                        template_values = add_test_to_template( template_values, in_query[0] )
                    except IndexError: # The test does not exist
                        self.redirect("/")

            potential_groups = set(
                itertools.chain( entity.test_groups, default_groups )
            )
            print potential_groups
            grouped_marks = get_grouped_marks( entity.id )

            # Add groups with levels for level dropdown
            template_values['user_levels'] = json.dumps( grouped_marks )

            # Add list of groups for group dropdown
            template_values['user_groups'] = []
            for group in grouped_marks:
                group_test_query = Test.query( Test.group == group['group'] ).order(-Test.level).fetch()
                try:
                    threshold = group_test_query[0]
                except:
                    threshold = 0
                print threshold
                for mark in grouped_marks:
                    potential_groups = potential_groups - set(group['group'])
                    if mark['group'] == group and mark["level"] >= threshold:
                        template_values['user_groups'].append( group )
            for group in potential_groups:
                template_values['user_groups'].append( group )

            if template_values["user_groups"] == []:
                template_values['error'] = "You may only create a test in a new category."

            path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'create.html' ) )
            self.response.out.write( template.render( path, template_values ))
        return

    def post(self):
        user = users.get_current_user()
        entity = Entity.query( Entity.id == user.user_id() ).fetch()[0]
        test_query = Test.query( ancestor = ndb.Key('Entity', entity.id ) )
        test_query = test_query.filter( Test.id == self.request.get( 'id' ) ).fetch()

        if len(test_query) > 0:
            test = test_query[0]
            test.modified = datetime.datetime.now()
        else:
            test = Test( parent = ndb.Key('Entity', entity.id ) )
            test.created = datetime.datetime.now()
            test.times_taken = 0
            test.total_score = 0
            test.num_marked = 0
            test.average_rating = 0
            test.open = True
            test.author_id = user.user_id()

        test.title = self.request.get( 'title' )
        test.description = self.request.get( 'description' )
        test.group = self.request.get( 'group' )
        test.level = int(self.request.get( 'level' ))

        # Define rules for what is and isn't a valid group
        try:
            assert re.match('^[a-z0-9_]{2,16}$', self.request.get( 'group' )) is not None
        except:
            # If the group is invalid, try again
            template_values = get_template_values( self )
            template_values['error'] = """There was an error with the group entered. Please ensure it uses only
                                       lowercase letters, numbers, and underscores."""
            template_values['user_groups'] = set(
                itertools.chain( entity.test_groups, default_groups )
            )
            template_values['user_levels'] = json.dumps( get_grouped_marks( ndb.Key( "Entity", entity.id ) ))
            template_values = add_test_to_template(template_values, test)
            path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'create.html' ) )
            self.response.out.write( template.render( path, template_values ))
            return

        # Define rules for what is and isn't a valid level for the user to be posting in.
        user_level = get_user_group_level( get_grouped_marks( entity.id ), test.group )
        max_test_query = Test.query( Test.group == test.group ).order(-Test.level).fetch()
        print max_test_query

        try:
            max_test_level = max_test_query[0].level / 2
        except IndexError:
            max_test_level = 0
        print "USER LEVEL: ", user_level
        print "MAX TEST L: ", max_test_level
        print "TEST LEVEL: ", test.level

        print (user_level) > max_test_level

        if user_level < max_test_level or user_level < test.level:
            # User level is not high enough.
            template_values = get_template_values( self )
            if user_level < max_test_level:
                template_values['error'] = """You must be at least level %d in %s to create a test.""" \
                                       % ( math.floor(max_test_level), test.group)
            elif user_level < test.level:
                template_values['error'] = """You must be at least level %d in %s to create a level %d test .""" \
                                       % ( test.level, test.group, test.level)
            template_values['user_groups'] = set(
            itertools.chain( entity.test_groups, default_groups )
            )
            template_values['user_levels'] = json.dumps( get_grouped_marks( entity_id=entity.id ) )
            template_values = add_test_to_template(template_values, test)
            path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'create.html' ) )
            self.response.out.write( template.render( path, template_values ))
            return


        # Create an id and save the test if the group is valid
        test.id = str( test.put().id() )
        test.put()

        # Keep track of which test groups a user has used
        if test.group not in entity.test_groups:
            entity.test_groups.append(test.group)
            entity.put()

        self.redirect('/t/%s' % test.id )
        return

class UserProfile( webapp2.RequestHandler ):
    
    def get(self, profile_to_get=None):
        template_values = get_template_values( self )
        user = users.get_current_user()
        if user:
            
            if not profile_to_get or profile_to_get ==  user.user_id():
                entity_query = Entity.query( Entity.id == user.user_id() ).fetch() 
            else:
                entity_query = Entity.query( Entity.id == profile_to_get ).fetch()
                if len(entity_query) < 1:
                    entity_query = Entity.query( Entity.display_name == profile_to_get ).order(-Entity.created).fetch()
                    
            if len(entity_query) < 1:
                self.redirect('/')
                return
                
            entity = entity_query[0]
                      
            if len(entity_query) > 0:
                if user.user_id() == entity.id:
                    template_values['this_user'] = True
                template_values = add_entity_to_template(template_values, entity, self.request)
                path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'profile.html' ) )
                self.response.out.write( template.render( path, template_values ))
                return
        self.redirect('/')
        return
        
class TestView( webapp2.RequestHandler ):
    logger = logging.getLogger("TestView")
    
    def get(self, test_to_get=None):
        template_values = get_template_values( self )
        user = users.get_current_user()

        if not test_to_get:
            self.logger.debug("No test was provided for lookup")
            self.redirect('/')
            return
        else:
            try:
                test = Test.query( Test.id == test_to_get).fetch(1)[0]
            except IndexError:
                self.logger.debug("Invalid Test ID")
                self.redirect('/')
            else:
                if user:
                    template_values = add_entity_to_template(
                        template_values,
                        Entity.query( Entity.id == user.user_id() ).fetch(1)[0]
                    )
                    user_level = get_user_group_level(
                        get_grouped_marks( user.user_id() ),
                        test.group
                    )
                    if user_level == None:
                        user_level = 1

                    template_values['user_level'] = user_level
                    if user_level < test.level:
                        template_values['locked'] = True
                    try:
                        mark_query = Mark.query( ancestor = ndb.Key("Entity", user.user_id() ) )
                        mark = mark_query.filter( Mark.test.id == test.id ).fetch(1)[0]
                        template_values = add_mark_to_template( template_values, mark )
                        if (datetime.datetime.now() - mark.modified) < datetime.timedelta(hours=24) or mark.complete:
                            template_values['locked'] = True
                    except IndexError:
                        self.logger.debug( "No mark found" )
                        template_values = add_test_to_template( template_values, test )
                    finally:    
                        if test.author_id == user.user_id():
                            template_values['is_test_marker'] = True
                            template_values['locked'] = True
                            test_marker = Entity.query( Entity.id == user.user_id() ).fetch()[0]
                            template_values['to_be_marked'] = get_to_be_marked( test_marker, test )
                            template_values['name'] = test_marker.display_name
                            template_values['current_user'] = user.user_id()                
                else: 
                    template_values['locked'] = True
                    template_values['visitor'] = True
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
                this_mark.rated = False
                this_mark.rating = 0
                test.times_taken += 1
                test.put()
                
            this_mark.response = self.request.get( 'response' )
            this_mark.complete = False
            this_mark.modified = datetime.datetime.now()
            this_mark.id = test_id + user.user_id()
            this_mark.marker_entity = Entity.query( Entity.id == author_id ).fetch()[0]
            this_mark.taker_entity = Entity.query( Entity.id == user.user_id() ).fetch()[0]
            send_email( this_mark.marker_entity.user.email() , test,  "Test-Answer")
            this_mark.put()

        self.redirect( '/t/%s' % test_id )
        return
        
class MarkView( webapp2.RequestHandler ):

    def post( self, in_test_id ):
        path = urlparse.urlsplit(self.request.referrer).path
        author_id = self.request.get("author_id")
        test_id = self.request.get("test_id")
        mark_id = self.request.get("mark_id")
        address = self.request.get("mark_address")
        comment = self.request.get("comment")
        mark = self.request.get("mark")
        
        author_entity = Entity.query( Entity.id == author_id ).fetch(1)[0]
        test_entity = Test.query( Test.id == test_id ).fetch(1)[0]        
        mark_entity = Mark.query( ancestor = ndb.Key("Entity", mark_id) )
        mark_entity = mark_entity.filter( Mark.test.id == test_id ).fetch(1)[0]
 
        mark_entity.marker_entity = author_entity
        mark_entity.test = test_entity
        mark_entity.comment = comment
        mark_entity.mark = int(mark)
        test_entity.total_score += mark_entity.mark
        test_entity.num_marked += 1
        mark_entity.modified = datetime.datetime.now()
        mark_entity.complete = True
        mark_entity.put()
        send_email( address, test_entity, "Answer-Response")
        test_entity.put()
        self.redirect( path )
        return
        
class MarkRating( webapp2.RequestHandler ):
    
    def post(self):
        user = users.get_current_user()
        mark_id = self.request.get("mark_id")
        rating = int(self.request.get("rating"))
        try:
            mark = Mark.query( ancestor = ndb.Key("Entity", user.user_id()) ).filter( Mark.id == mark_id ).fetch()[0]
        except:
            mark = None
        if mark:
            mark.rating = int( rating )
            mark.rated = True
            mark.put()

        self.redirect("/t/%s" % mark_id)
            
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

## Helper Functions
def add_mark_to_template( template_values, in_mark ):
    """Combines Mark object properties into template_values"""
    template_values = add_entity_to_template( template_values, in_mark.marker_entity )
    # the updated_test value is required here or else the Test that is returned is the Test taken, not the current test
    updated_test = Test.query( Test.id == in_mark.test.id ).fetch(1)[0]
    template_values = add_test_to_template( template_values, updated_test )
    template_values['complete'] = in_mark.complete
    template_values['response'] = in_mark.response
    template_values['comment'] = in_mark.comment
    template_values['mark'] = in_mark.mark
    template_values['mark_id'] = in_mark.id
    template_values['mark_created'] = in_mark.created
    template_values['mark_modified'] = in_mark.modified
    template_values['rating'] = in_mark.rating
    template_values['rated'] = in_mark.rated
    return template_values
    
def add_entity_to_template( template_values, in_entity, request=None, open=None ):
    """Combines Entity object properties into template_values"""
    template_values['name'] = in_entity.display_name
    template_values['id'] = in_entity.id
    template_values['created'] = in_entity.created
    template_values['modified'] = in_entity.modified
    template_values['bio'] = in_entity.bio
    template_values['grouped_marks'] = get_grouped_marks_list( entity_id = in_entity.id )
    template_values['gravatar'] = "http://www.gravatar.com/avatar/" + hashlib.md5(in_entity.user.email().lower()).hexdigest() + "?s=60"
    ## Lists of Tests
    if request: 
        # This might be an odd way of defining this, but I want to have to ask for these lists
        # instead of providing them to each page that loads an entity.
        entity_key = ndb.Key('Entity', template_values['id'])
        # Get cursors, if available (two won't be for sure)
        completed_cursor=Cursor(urlsafe=request.get('next_completed'))
        in_progress_cursor=Cursor(urlsafe=request.get('next_in_progress'))
        created_cursor=Cursor(urlsafe=request.get('next_created'))
        
        template_values['completed'] = get_marks( num=5, start_cursor=completed_cursor, ancestor_key=entity_key, mark_complete=True )
        template_values['in_progress'] = get_marks( num=5, start_cursor=in_progress_cursor, ancestor_key=entity_key, mark_complete=False )
        template_values['created_tests'] = get_tests( num=5, start_cursor=created_cursor, ancestor_key=entity_key, open=open )

    return template_values
    
def add_test_to_template( template_values, in_test ):
    """Combines Test object properties into template_values"""
    template_values['test_id'] = in_test.id
    template_values['title'] = in_test.title
    template_values['description'] = in_test.description
    template_values['group'] = in_test.group
    template_values['level'] = in_test.level
    template_values['test_created'] = in_test.created
    template_values['test_modified'] = in_test.modified
    template_values['author_id'] = in_test.author_id
    template_values['author_name'] = Entity.query( Entity.id == in_test.author_id ).fetch(1)[0].display_name
    template_values['times_taken'] = in_test.times_taken
    template_values['total_score'] = in_test.total_score
    template_values['num_marked'] = in_test.num_marked
    template_values['open'] = in_test.open
    if in_test.num_marked > 0:
        template_values['average_mark'] = template_values['total_score'] / template_values['num_marked']
    mark_list = Mark.query( Mark.test.id == in_test.id ).filter( Mark.rating > -1 ).fetch()
    template_values['num_ratings'] = len(mark_list)
    if template_values['num_ratings'] > 0:
        template_values['average_rating'] =  sum([mark.rating for mark in mark_list]) / template_values['num_ratings']
        if template_values['average_rating'] is not in_test.average_rating:
            save_average_rating( in_test.id, template_values['average_rating'])
    return template_values
   
def save_average_rating( test_id, avg ):
    test = Test.query( Test.id == test_id ).fetch(1)[0]
    test.average_rating = avg
    test.put()
    return
    
def get_to_be_marked( entity, test=None, num=None ):
    """Retrieves the responses from other entities that need to have marks assigned for tests created by this entity"""
    mark_query = Mark.query( Mark.marker_entity.id == entity.id )
    mark_query = mark_query.filter( Mark.complete == False )
    if test:
        mark_query = mark_query.filter( Mark.test.id == test.id )
        mark_query = mark_query.filter( Mark.test.author_id == entity.id )
    
    if not num:
        return mark_query.fetch()
    else:
        return mark_query.fetch( num )
        
def get_marked( entity, num=None ):
    """Retrieves the responses from other entities that need to have marks assigned for tests created by this entity"""
    mark_query = Mark.query( Mark.marker_entity.id == entity.id )
    mark_query = mark_query.filter( Mark.complete == True )
    if not num:
        return mark_query.fetch()
    else:
        return mark_query.fetch( num )

def get_grouped_marks_list( entity_id ):
    """Returns a list of summary of the marks in each group
        This only provides values for groups that the user has been given
       return {{'group_name':name, 'tests_taken':tests_taken, 'total_score':num }, {...}, ... }
    """
    grouped_marks = []
    groups = set()
    mark_list = Mark.query( ancestor = ndb.Key( "Entity", entity_id) ).filter( Mark.complete == True ).order( -Mark.created ).fetch()
    for mark in mark_list:
        groups_length = len(groups)
        groups.update( mark.test.group )
        if groups_length < len(groups):
            # If the set of groups got longer, add a new dict to the list
            grouped_marks.append({
                'name': mark.test.group,
                'tests_taken': 1,
                'total_score': mark.mark * mark.test.level,
            })
        else:
            for group in grouped_marks:
                if group['name'] == mark.test.group:
                    group['tests_taken'] += 1
                    group['total_score'] += mark.mark * mark.test.level

    for group in grouped_marks:
        if group['total_score'] is not None and group['total_score'] > 0:
            group['level'] = math.floor( math.log( float(group['total_score']),2 ) )
            group['level_progress'] = (math.log( group['total_score'],2 ) - group['level']) * 100
        else:
            group['total_score'] = 0
            group['level'] = 1
            group['level_progress'] = 0
    return grouped_marks

def get_grouped_marks( entity_id ):
    """Returns a list of summary of the marks in each group
        This list will return all available lgroups, even if the level is 0.
    """
    grouped_marks = []
    groups = set()
    mark_list = Mark.query( ancestor = ndb.Key( "Entity", entity_id )).filter( Mark.complete == True ).order( -Mark.created ).fetch()
    entity = Entity.query( Entity.id == entity_id).fetch()[0]

    group_list = []
    for mark in mark_list:
        groups_length = len(groups)
        groups.update( mark.test.group )
        if groups_length < len(groups):
            # If the set of groups got longer, add a new dict to the list
            grouped_marks.append({
                'group' : mark.test.group,
                'level' : mark.test.level,
                'level_progress' : 0,
                'tests_taken' : 0,
                'total_score' : 0,
            })
        else:
            for group in grouped_marks:
                if group['group'] == mark.test.group:
                    group['tests_taken'] += 1
                    group['total_score'] += mark.mark * mark.test.level
                    group_list.append( mark.test.group )

    for group in grouped_marks:
        if group['total_score'] is not None and group['total_score'] > 0:
            group['level'] = math.floor( math.log( float(group['total_score']),2 ) )
            group['level_progress'] = (math.log( group['total_score'],2 ) - group['level']) * 100
        else:
            group['total_score'] = 0
            group['level'] = 1
            group['level_progress'] = 0

    unused_defaults = set( itertools.chain( entity.test_groups, default_groups )) - set( [ group['group'] for group in grouped_marks ] )
    for group in unused_defaults:
        grouped_marks.append( {'group':group,'level':1,'level_progress':0} )
    return grouped_marks


def get_user_group_level( level_groups, group_name ):
    for group in level_groups:
        if group['group'] == group_name:
            return group['level']
    return 1
        
def get_marks( num=None, start_cursor=None, ancestor_key=None, mark_complete=None):
    """Retrieves the num most recent marks, starting at start_cursor, only for the ancestor if provided, and only completed or not-completed tests if mark_complete is provided"""
    if ancestor_key:
        # This checks for only marks created by this entity
        mark_query = Mark.query( ancestor = ancestor_key ).order( -Mark.test.created )
    else:        
        mark_query = Mark.query().order( -Mark.test.created )
    if mark_complete is not None:
        # Filter completed marks based on mark_complete -> default is None => all marks
        mark_query = mark_query.filter( Mark.complete == mark_complete )
    if start_cursor:
        # Set the query start to the cursor location, if provided
        marks, next_cursor, more = mark_query.fetch_page(num, start_cursor=start_cursor)
        try:
            return { 'marks':marks, 'next':next_cursor.urlsafe(), 'more':more }
        except:
            return { 'marks':marks, 'next':None, 'more':False }
    elif num: 
        # Otherwise return the number of requested results
        return mark_query.fetch( num )
    # Or all if no num was specified
    return mark_query.fetch()   

        
def get_tests( num=None, start_cursor=None, ancestor_key=None, open=None ):
    """Retrieves the num most recent tests, starting at start_cursor, and only for the ancestor if provided"""
    if ancestor_key:
        # This checks for only tests created by this entity
        test_query = Test.query( ancestor = ancestor_key ).order( -Test.created )
    else:
        test_query = Test.query().order( -Test.created )
    if open is not None:
        # filter open or closed tests as needed
        test_query = test_query.filter( Test.open == open )
    if start_cursor:
        # Set the query start to the cursor location if provided
        tests, next_cursor, more = test_query.fetch_page(num, start_cursor=start_cursor)
        try:
            return { 'tests':tests, 'next':next_cursor.urlsafe(), 'more':more }
        except:
            return { 'tests':tests, 'next':None, 'more':False }
    elif num: 
        # Otherwise return the number of requested results
        return test_query.fetch( num )
    # Or all if no num was specified
    return test_query.fetch()        
        
def get_template_values( self ):
    """Constructs and returns a dict of common values needed by all or nearly all templates"""
    user = users.get_current_user()
    
    template_values= {
        'date'      : datetime.datetime.now(),
        'nav_urls'  : get_navigation_urls( self, user ),
    }
    if user:
        try:
            entity = Entity.query( Entity.id == user.user_id() ).fetch()[0]
            template_values['user_name'] = entity.display_name
            template_values['bio'] = entity.bio
        except:
            # User isn't an entity yet
            pass
        template_values['user'] = user
        template_values['user_id'] = user.user_id()
        template_values['nav_grav'] = "http://www.gravatar.com/avatar/" + hashlib.md5(user.email().lower()).hexdigest() + "?s=36"
    else:
        template_values['user'] = False
    return template_values

def get_navigation_urls( self, user ):
    """Constructs and returns a dict of common urls used for navigation"""
    navigation_urls = {
        'home'  : '/',
        'create_test': '/c',
        'profile': '/u',
        'tests': '/t',
    }
    if user:
        navigation_urls['logout'] = users.create_logout_url( '/' )
    else:
        navigation_urls['login'] = users.create_login_url( '/login' )
    return navigation_urls

def send_email( to, test, type ):
    """Sends an email"""
    site_name = "Densando"
    site_address = "densandodev.appspot.com"
    address_local = "do_not_reply"
    address_suffix = "densandodev.appspotmail.com"
    
    if type == "Test-Answer":
        subject = "Someone has submitted an answer to %s" % test.title
    elif type == "Answer-Response":
        subject = "Your answer to %s has been marked" % test.title
 
    email_message = mail.EmailMessage(
        sender = "%s <%s@%s>" % ( site_name, address_local, address_suffix ),
        subject = subject,
        to = to,
        body = subject + "\n\n" + site_address + "/t/" + test.id,
    )
    email_message.send()
    return True

# Run Runaway!
app = webapp2.WSGIApplication( [
    ( '/'  , MainPage ),
    ( '/login', LoginHandler ),
    ( '/register', RegistrationHandler ),
    ( '/preferences', RegistrationHandler ),
    ( '/c/([^/]+)', CreateAlterTest ),
    ( '/c', CreateAlterTest ),
    ( '/u/([^/]+)', UserProfile ),
    ( '/u', UserProfile ),
    ( '/t/([^/]+)/([tf])', OpenCloseTest ),
    ( '/t/([^/]+)', TestView ),
    ( '/t', TestView ),
    ( '/m/([^/]+)', MarkView ),
    ( '/m', MarkView ),    
    ( '/r', MarkRating ),
], debug = True)

def main():
    run_wsgi_app(app)

if __name__ == '__main__':
    main()
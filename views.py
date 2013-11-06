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

## Imports from GAE
from google.appengine.ext.webapp import template
from google.appengine.api import users, memcache, mail, search
from google.appengine.ext import ndb
from google.appengine.datastore.datastore_query import Cursor

## Imports from this app
from models import Test, Entity, Mark
from helpers import \
    add_mark_to_template, \
    add_entity_to_template, \
    add_test_to_template, \
    get_to_be_marked, \
    get_grouped_marks, \
    get_user_group_level, \
    get_tests, \
    get_template_values, \
    send_email, \
    template_dir, \
    default_groups

## Views to Render
class MainPage(webapp2.RequestHandler):
    logger = logging.getLogger("MainPage")
    page_depth = 7

    def get(self):
        template_values = get_template_values( self )
        start_cursor = Cursor(urlsafe=self.request.get('next'))
        # only return open tests with open=True
        template_values['recent_tests'] = get_tests(
            num=self.page_depth,
            start_cursor=start_cursor,
            open=True
        )
        path = os.path.join( os.path.dirname(__file__), os.path.join( template_dir, 'main.html' ) )
        self.response.out.write( template.render( path, template_values ))
        return

    def post(self):
        template_values = get_template_values( self )
        user = users.get_current_user()

        if self.request.get('next'):
            cursor = search.Cursor(web_safe_string=self.request.get('next'))
        else:
            cursor = search.Cursor()

        q = query = self.request.get("search-text").replace(',',"")
        order = self.request.get("search-order")
        completed = True if self.request.get("search-completed") == "on" else False

        template_values["query_values"] = {
            'query':query,
            'order':order,
            'completed':completed,
        }

        if order == "rating":
            sort_exp = search.SortExpression( expression='rating', direction=search.SortExpression.DESCENDING, default_value=0)
        elif order == "times_taken":
            sort_exp = search.SortExpression( expression='times_taken', direction=search.SortExpression.DESCENDING, default_value=0)
        elif order == "date_inc":
            sort_exp = search.SortExpression( expression='date', direction=search.SortExpression.DESCENDING, default_value=0)
        elif order == "date_dec":
            sort_exp = search.SortExpression( expression='date', direction=search.SortExpression.ASCENDING, default_value=0)
        elif order == "level_dec":
            sort_exp = search.SortExpression( expression='level', direction=search.SortExpression.DESCENDING, default_value=0)
        elif order == "level_inc":
            sort_exp = search.SortExpression( expression='level', direction=search.SortExpression.ASCENDING, default_value=0)

        query_options = search.QueryOptions(
            limit = self.page_depth,
            cursor = cursor,
            sort_options = search.SortOptions(expressions=[sort_exp,]),
        )

        query_obj = search.Query(query_string=query, options=query_options)
        results = search.Index(name="tests").search(query=query_obj)
        template_values["query_results"] = []

        for document in results:
            test = Test.query( Test.id == document.doc_id ).get()
            if completed and user:
                # If the "Hide completed" checkbox is selected by the user
                if Mark.query( Mark.taker_entity.id == user.user_id(), Mark.test.id == test.id ).get() != None :
                    # And a Mark has been created
                    continue # Don't add it to the list.
                    # If this continue is active, this selects out TAKEN tests
                    # Otherwise , this if statement selects out MARKED tests
                    if Mark.query( Mark.complete == False ).get() == None:
                        # And the Test has been marked as completed for this user.
                        continue # Don't add it to the list.
            template_values["query_results"].append( test )

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
            template_values['mark_groups'] = get_grouped_marks( user.user_id() )
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
        if not entity.display_name:
            posted_name = self.request.get( 'display_name' )
        else:
            posted_name = entity.display_name

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
            entity = Entity.query( Entity.id == user.user_id() ).get()
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
        entity = Entity.query( Entity.id == user.user_id() ).get()
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

        if user_level < max_test_level or user_level < test.level:
            # User level is not high enough.
            template_values = get_template_values( self )
            if user_level < max_test_level:
                template_values['error'] = "You must be at least level %d in %s to create a test." \
                                           "You are only level %d." \
                                           % ( math.floor(max_test_level), test.group, user_level)
            elif user_level < test.level:
                template_values['error'] = """You must be at least level %d in %s to create a level %d test .""" \
                                       % ( test.level, test.group, test.level)
            template_values['user_groups'] = set( itertools.chain( entity.test_groups, default_groups ) )
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

        # Add/Alter this test's Document in the search index
        test_as_document = search.Document(
                doc_id = test.id,
                fields = [
                    search.AtomField( name="group", value=test.group ),
                    search.TextField( name="title", value=test.title ),
                    search.NumberField( name="times_taken", value=test.times_taken ),
                    search.DateField( name="date", value=test.created ),
                    search.NumberField( name="level", value=test.level ),
                    search.NumberField( name="rating", value=test.average_rating ),
                ]
            )
        try:
            index = search.Index(name="tests")
            index.put( test_as_document )
        except search.Error:
            logging.info("Index put failed")

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

class AddTestGroup( webapp2.RequestHandler ):
    logger = logging.getLogger("AddTestGroup")

    def post(self):
        group_name = self.request.get('group_name')
        user = users.get_current_user()
        entity = Entity.query( Entity.id == user.user_id() ).get()
        try:
            assert re.match('^[a-z0-9_]{2,16}$', group_name ) is not None
        except:
            self.redirect('/preferences')
        else:
            if group_name not in entity.test_groups:
                entity.test_groups.append(group_name)
                entity.put()
            time.sleep(0.1) # Need some time to ensure consistency.
        self.redirect('/preferences')


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
                            test_marker = Entity.query( Entity.id == user.user_id() ).get()
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
            test = Test.query( Test.id == test_id ).get()
            mark_query = Mark.query( ancestor = ndb.Key("Entity", user.user_id() ) )
            mark_query = mark_query.filter( Mark.test.id == test.id )

            this_mark = mark_query.get()

            if this_mark == None:
                print "IndexError"
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
            this_mark.marker_entity = Entity.query( Entity.id == author_id ).get()
            this_mark.taker_entity = Entity.query( Entity.id == user.user_id() ).get()
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

        author_entity = Entity.query( Entity.id == author_id ).get()
        test_entity = Test.query( Test.id == test_id ).get()
        mark_entity = Mark.query( ancestor = ndb.Key("Entity", mark_id) )
        mark_entity = mark_entity.filter( Mark.test.id == test_id ).get()

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
            mark = Mark.query( ancestor = ndb.Key("Entity", user.user_id()) ).filter( Mark.id == mark_id ).get()
        except:
            mark = None
        if mark:
            mark.rating = int( rating )
            mark.rated = True
            mark.put()

        self.redirect("/t/%s" % mark_id)

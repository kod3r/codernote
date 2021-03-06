from models import Note, HashPublish, FlowPublish, NoteInvite
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseServerError
from django.shortcuts import render_to_response
from forms import NoteForm
from django.core import serializers
from datetime import datetime
from django.contrib.auth.models import User
import re, md5, time
from django.conf import settings
from pygments.lexers import get_all_lexers
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_page
from django.db.models import signals
from userskins.models import SkinPreference

try:
    from mailer import send_mail
except ImportError:
    from django.core.mail import send_mail

def select_skin(request, skin):
    hrr = HttpResponseRedirect("/account/")
    hrr.set_cookie("userskins", skin)
    if request.user.is_authenticated():
        try:
            sp = SkinPreference.objects.get(user=request.user)
            sp.skin=skin
            sp.save()
        except SkinPreference.DoesNotExist:
            SkinPreference.objects.create(user=request.user, skin=skin)
    return hrr

def select_bw_skin(request):
    return select_skin(request, "bw")

def select_warm_skin(request):
    return select_skin(request, "warm")

def select_dark_skin(request):
    return select_skin(request, "dark")


def add_initial_notes(sender, instance, signal, *args, **kwargs):
    if instance.notes.all().count():
        return
    title = u"Welcome!"
    slug = u"welcome"
    tags = u"help, welcome"
    type= u"markdown"
    type_detail = u" "
    text = u"""
### Welcome to Codernote

[contact]: http://codernote.com/contact/

I'm glad you've stopped by. Codernote is a tool that I created
to solve my organization and collaboration needs, and that I use
everyday. Codernote is currently growing and changing quickly, as it becomes
an increasingly powerful tool for organizing, sharing and editing
notes.

There are two points I'd like to emphasize as you get started
playing with Codernote:

1.  I've tried to make every decision in favor of users: you.
    If there are features or decisions that you don't like,
    please let me know. The [contact form][contact] is the easiest
    way to get in touch, and goes directly to my mailbox.

2.  This will be a paid service. It won't be an expensive paid service
    --it may set you back a latte or two--but it will not be free.
    Certainly, there will be a free trial period.

    If you don't believe Codernote is worth a bit of your money
    each month, please let me know what could be done to pass
    that threshold.

I hope you enjoy Codernote, and please let me know how I can
help improve your experience.

Will (lethain@gmail.com)


"""
    n = Note.objects.create(title=title,
                        slug=slug,
                        tags=tags,
                        type=type,
                        type_detail=type_detail,
                        text=text)
    n.owners = [instance]
    n.save()
                        
                        

signals.post_save.connect(add_initial_notes, sender=User)


def case_insensitive_alpha(a,b):
    a = a.lower()
    b = b.lower()
    if a>b:
        return 1
    elif a == b:
        return 0
    return -1

LEXERS = [ tuple[0] for tuple in get_all_lexers() ]
LEXERS.sort(case_insensitive_alpha)


""" Utilities """

def slugify(string):
    string = re.sub('[\s.-]+', '_', string)
    string = re.sub('\W', '', string)
    return string.strip('_.- ').lower()

def find_slug_for(string):
    i = 0
    new_str = string
    while (Note.objects.filter(slug=new_str).count() > 0):
        new_str = u"%s%s" % (string, i)
        i = i + 1
    return new_str

def make_tags_uniform(string):
    return re.sub('[ ,]+',', ',string)

""" Note """

def note_list(request):
    'Non-Ajax view.'
    if request.user.is_authenticated():
        notes = Note.objects.filter(owners=request.user)
        fields = ('owners','sticky','title','slug','tags','created','start','end','type')
        serialized = serializers.serialize("json", notes,fields=fields)
        invite_count = NoteInvite.objects.filter(user=request.user).count()
        extra = {'serialized':serialized, 'invites':invite_count }
    else:
        extra = {}
    return render_to_response('codernote/note_list.html', extra, 
                              context_instance=RequestContext(request))

@login_required
def note_detail(request, slug):
    'Non-Ajax view.'
    note = Note.objects.filter(owners=request.user).get(slug=slug)
    extra = {'object':note, 'lexers':LEXERS}
    return render_to_response('codernote/note_detail.html', extra,
                              context_instance=RequestContext(request))

@login_required
def note_create(request):
    'Non-Ajax view.'
    if request.method == 'POST':
        form = NoteForm(request.POST)
        if form.is_valid():
            new_note = form.save(commit=False)
            new_note.slug = find_slug_for(slugify(new_note.title))
            new_note.tags = make_tags_uniform(new_note.tags)
            new_note.text = "Fill me in!"
            new_note.type = "plain"
            new_note.save()
            new_note.owners = [request.user]
            form.save_m2m()
            return HttpResponseRedirect(new_note.get_absolute_url())
    else:
        form = NoteForm()
    extra = {'create_form':form}
    return render_to_response('codernote/note_create.html', extra,
                              context_instance=RequestContext(request))

@login_required
def note_info_all(request):
    pass

@login_required
def note_info(request, slug=None):
    pass



@login_required
def note_delete(request, slug=None):
    if slug is None:
        if request.POST.has_key('slug'):
            slug = request.POST['slug']
        else:
            return HttpResponseServerError('Failed to supply a slug.')
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponse("Failed to retrieve note.")
    if note.owners.all().count() == 1:
        note.delete()
        NoteInvite.objects.filter(note=note).delete()
    else:
        note.owners.remove(request.user)
    return HttpResponseRedirect("/")

@login_required
def note_update(request, slug=None):
    if slug is None:
        if request.POST.has_key('slug'):
            slug = request.POST['slug']
        else:
            return HttpResponseServerError('Failed to supply a slug.')
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponse("Failed to retrieve note.")
    updated = []
    if request.POST.has_key('title'):
        note.title = request.POST['title']
        updated.append('title')
    if request.POST.has_key('tags'):
        note.tags = make_tags_uniform(request.POST['tags'])
        updated.append('tags')
    if request.POST.has_key('text'):
        note.text = request.POST['text']
        updated.append('text')
    if request.POST.has_key('type'):
        note.type = request.POST['type']
        updated.append('type')
    if request.POST.has_key('type_detail'):
        note.type_detail = request.POST['type_detail']
        updated.append('type detail')
    if request.POST.has_key('start'):
        raw = request.POST['start'].split('/')
        year = int(raw[2])
        month = int(raw[0])
        day = int(raw[1])
        note.start = datetime(year, month, day)
        updated.append('start date')
    if request.POST.has_key('end'):
        raw = request.POST['end'].split('/')
        year = int(raw[2])
        month = int(raw[0])
        day = int(raw[1])
        note.end = datetime(year, month, day)
        updated.append('end date')

    note.save()
    msg = "Updated %s." % ", ".join(updated)
    return HttpResponse(msg)
    
@login_required
def note_render(request, slug=None):
    if slug is None:
        if request.POST.has_key('slug'):
            slug = request.POST['slug']
        else:
            return HttpResponseServerError('Failed to supply a slug.')
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponse("Failed to retrieve note.")
    return HttpResponse(note.render_text())

@login_required
def note_unsticky(request, slug=None):
    if slug is None:
        if request.POST.has_key('slug'):
            slug = request.POST['slug']
        else:
            return HttpResponseServerError('Failed to supply a slug.')
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponse("Failed to retrieve note.")
    note.sticky = False
    note.save()

    return HttpResponse(u"Unstickied note %s" % note.slug)

@login_required
def note_sticky(request, slug=None):
    if slug is None:
        if request.POST.has_key('slug'):
            slug = request.POST['slug']
        else:
            return HttpResponseServerError('Failed to supply a slug.')
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponse("Failed to retrieve note.")
    note.sticky = True
    note.save()

    return HttpResponse(u"Stickied note %s" % note.slug)

def extract_rev_data(rev):
    return {'date':rev._audit_timestamp,
            'id':rev._audit_id,
            'text':rev.text,
            }

@login_required
def note_revisions(request):
    if request.POST.has_key('slug'):
        slug = request.POST['slug']
    else:
        return HttpResponseServerError('Failed to supply a slug.')
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponse("Failed to retrieve note.")
    revs = note.history.all()
    revs = [extract_rev_data(x) for x in revs]
    extra = {'history':revs}
    return render_to_response('codernote/note_revisions.html', extra)

@login_required
def note_revision_delete(request):
    if request.POST.has_key('slug'):
        slug = request.POST['slug']
    else:
        return HttpResponseServerError('Failed to supply a slug.')
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponse("Failed to retrieve note.")
    if request.POST.has_key('id'):
        revision = note.history.get(_audit_id=request.POST['id'])
    else:
        return HttpResponseServerError('Failed to supply a revision id.')
    revision.delete()
    return HttpResponse("Revision deleted.")

@login_required
def note_revision_revert(request):
    if request.POST.has_key('slug'):
        slug = request.POST['slug']
    else:
        return HttpResponseServerError('Failed to supply a slug.')
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponse("Failed to retrieve note.")
    if request.POST.has_key('id'):
        revision = note.history.get(_audit_id=request.POST['id'])
    else:
        return HttpResponseServerError('Failed to supply a revision id.')
    note.text = revision.text
    note.save()
    return HttpResponse("Reverted successfully.")

""" Managing Note Invitations """

@login_required
def note_manage_invites(request):
    invites = NoteInvite.objects.filter(user=request.user)
    extra = {'obj_list':invites}
    return render_to_response('codernote/manage_invites.html',
                              extra,
                              context_instance=RequestContext(request))

@login_required
def note_accept_invite(request, pk):
    try:
        invite = NoteInvite.objects.get(pk=pk)
    except:
        return HttpResponseServerError("No such invitiation exists.")
    invite.note.owners.add(request.user)
    invite.note.save()
    pk = invite.id

    send_mail("%s accepted your note." % request.user.username,
              'Hello %s,\n\n%s has accepted your note "%s".\n\nThank you,\nCodernote' % (invite.sender.username, request.user.username, invite.note.title),
              settings.DEFAULT_FROM_EMAIL,
              [invite.sender.email],
              )
    invite.delete()
    return HttpResponse("%s" % pk)

@login_required
def note_reject_invite(request, pk):
    try:
        invite = NoteInvite.objects.get(pk=pk)
    except:
        return HttpResponseServerError("No such invitiation exists.")
    pk = invite.id
    invite.delete()
    return HttpResponse("%s" % pk)


""" Non-Authenticated Views """

def about(request):
    return render_to_response('codernote/about.html',
                              context_instance=RequestContext(request))

def help(request):
    return render_to_response('codernote/help.html',
                              context_instance=RequestContext(request))

""" Utility Methods """

def user_exists(request, username):
    if User.objects.filter(username__iexact=username).count() > 0:
        return HttpResponse("Exists.")
    else:
        return HttpResponseServerError("Doesn't exist.")

""" Config """

@login_required
def config(request):
    pass

""" Publishing """

@login_required
def share_note(request, slug, username):
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponseServerError("Failed to retrieve note.")
    try:
        user = User.objects.get(username__iexact=username)
    except:
        return HttpResponseServerError("Invalid username.")
    NoteInvite.objects.create(user=user, note=note, sender=request.user)
    send_mail("%s shared a note with you." % request.user.username,
              'Hello %s,\n\n%s has shared a note title %s with you. Visit http://codernote.com/note/invites/ to accept or refuse this note invitation.\n\nThank you,\nCodernote' % (user.username, request.user.username, note.title),
              settings.DEFAULT_FROM_EMAIL,
              [user.email],
              )

    return HttpResponse("Successful.")


@login_required
def flow_publish(request, slug):
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponseServerError("Failed to retrieve note.")
    x = FlowPublish(note=note, user=request.user)
    x.save()
    return HttpResponse(x.get_absolute_url())

@login_required
def flow_unpublish(request, slug):
    FlowPublish.objects.filter(user=request.user).filter(note__slug=slug).delete()
    return HttpResponse("Deleted.")

@login_required
def hash_publish(request, slug):
    try:
        note = Note.objects.filter(owners=request.user).get(slug=slug)
    except:
        return HttpResponseServerError("Failed to retrieve note.")
    hash = md5.md5("%s%s" % (time.time(), note.title)).hexdigest()[:20]
    x = HashPublish(note=note, hash=hash, user=request.user)
    x.save()
    return HttpResponse(hash)

@login_required
def hash_unpublish(request, slug):
    HashPublish.objects.filter(user=request.user).filter(note__slug=slug).delete()
    return HttpResponse("Deleted.")

@cache_page(60 * 30)
def public_hash(request, hash):
    pub = HashPublish.objects.get(hash=hash)
    return render_to_response('codernote/public_hash.html',
                              {'object':pub.note},
                              context_instance=RequestContext(request))

@cache_page(60 * 30)
def public_flow(request, user):
    pub = FlowPublish.objects.filter(user__username__iexact=user)
    user = User.objects.get(username__iexact=user)
    return render_to_response('codernote/public_flow.html',
                              {'objects':pub, 'writer':user},
                              context_instance=RequestContext(request))

@cache_page(60 * 30)
def public_flow_detail(request, user, slug):
    pub = FlowPublish.objects.filter(user__username__iexact=user).filter(note__slug=slug)[0]
    return render_to_response('codernote/public_flow_detail.html',
                              {'object':pub.note,'writer':pub.user},
                              context_instance=RequestContext(request))

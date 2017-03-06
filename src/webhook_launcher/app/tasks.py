# Copyright (C) 2013 Jolla Ltd.
# Contact: Islam Amer <islam.amer@jollamobile.com>
# All rights reserved.
# 
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import json

from webhook_launcher.app.models import (LastSeenRevision, QueuePeriod)
from webhook_launcher.app.boss import launch_notify, launch_build


def handle_commit(mapobj, lsr, user, notify=False):

    lsr.tag = ""
    lsr.handled = False
    lsr.save()

    if not notify:
        return

    # lsr.payload is already a json string if it exists
    try:
        payload=json.loads(lsr.payload)
        num_commits=len(payload["commits"])
    except: # currently handle_commit is only called from 'real'
            # commits and not the Admin UI so this shouldn't happen
            # but...
        payload = None
        num_commits = "No payload available. Unknown number of"

    message = "%s commit(s) pushed by %s to %s branch of %s" % (num_commits, user, mapobj.branch, mapobj.repourl)
    if not mapobj.mapped:
        message = "%s, which is not mapped yet. Please map it." % message

    fields = mapobj.to_fields()
    fields['msg'] = message
    print message
    launch_notify(fields)


def trigger_build(mapobj, user, lsr=None, tag=None, force=False):

    if lsr is None:
        lsr, created = LastSeenRevision.objects.get_or_create(mapping=mapobj)

    # Only fire for projects which allow webhooks. We can't just
    # rely on validation since a Project may forbid hooks after
    # the hook was created
    if mapobj.project_disabled:
        print "Project has build disabled"
        return

    build = mapobj.build and mapobj.mapped
    delayed = False
    skipped = False
    qp = None

    if build:
        if not force:
            if lsr.handled and lsr.tag == tag:
                print "build already handled, skipping"
                build = False
                skipped = True

        # Find possible queue period objects
        qps = QueuePeriod.objects.filter(projects__name=mapobj.project,
                                         projects__obs__pk=mapobj.obs.pk)
        for qp in qps:
            if qp.delay() and not qp.override(webuser=user):
                print "Build trigger for %s delayed by %s" % (mapobj, qp)
                print qp.comment
                lsr.handled = False
                build = False
                delayed = True
                break

    # handle_build actually launches a build process
    msg = handle_build(mapobj, user, lsr, force, skipped, delayed, qp)
    return msg

def handle_build(mapobj, user=None, lsr=None, force=None, skipped=False, delayed=False, qp=None):

    build = mapobj.build and mapobj.mapped

    if lsr is None:
        lsr = mapobj.lsr
  
    if user is None:
        user = mapobj.user.username
  
    if lsr.tag:
        message = "Tag %s" % lsr.tag
        if force:
            message = "Forced build trigger for %s" % lsr.tag
    else:
        message = "%s" % mapobj.rev_or_head
        if force:
            message = "Forced build trigger for %s" % mapobj.rev_or_head
  
    message = "%s by %s in %s branch of %s" % (message, user, mapobj.branch,
                                               mapobj.repourl)
    if not mapobj.mapped:
        message = "%s, which is not mapped yet. Please map it." % message
    elif build:
        message = ("%s, which will trigger build in project %s package "
                   "%s (%s/package/show?package=%s&project=%s)" % (message,
                    mapobj.project, mapobj.package, mapobj.obs.weburl,
                    mapobj.package, mapobj.project))
  
    elif skipped:
        message = "%s, which was already handled; skipping" % message
    elif qp and delayed:
        message = "%s, which will be delayed by %s" % (message, qp)
        if qp.comment:
            message = "%s\n%s" % (message, qp.comment)
  
    if mapobj.notify:
        fields = mapobj.to_fields()
        fields['msg'] = message
        launch_notify(fields)
  
    if build:
        fields = mapobj.to_fields()
        fields['branch'] = mapobj.branch
        fields['revision'] = lsr.revision
        launch_build(fields)
        lsr.handled = True

    lsr.save()
 
    return message


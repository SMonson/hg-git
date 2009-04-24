import os, errno, sys, time, datetime
import dulwich
from dulwich.repo import Repo
from dulwich.client import SimpleFetchGraphWalker
from hgext import bookmarks
from mercurial.i18n import _
from mercurial.node import bin, hex, nullid
from mercurial import hg, util, context, error

class GitHandler(object):
    
    def __init__(self, dest_repo, ui):
        self.repo = dest_repo
        self.ui = ui
        git_dir = os.path.join(self.repo.path, 'git')
        self.git = Repo(git_dir)
        
    def fetch(self, git_url):
        self.ui.status(_("fetching from git url: " + git_url + "\n"))
        self.export_git_objects()
        self.fetch_pack(git_url)
        self.import_git_objects()
    
    def fetch_pack(self, git_url):
        client, path = self.get_transport_and_path(git_url)
        graphwalker = SimpleFetchGraphWalker(self.git.heads().values(), self.git.get_parents)
        f, commit = self.git.object_store.add_pack()
        try:
            determine_wants = self.git.object_store.determine_wants_all
            refs = client.fetch_pack(path, determine_wants, graphwalker, f.write, sys.stdout.write)
            f.close()
            commit()
            self.git.set_refs(refs)
        except:
            f.close()
            raise    

    def import_git_objects(self):
        self.ui.status(_("importing Git objects into Hg\n"))
        # import heads as remote references
        todo = []
        done = set()
        convert_list = []
        
        # get a list of all the head shas
        for head, sha in self.git.heads().iteritems():
            todo.append(sha)
        
        # traverse the heads getting a list of all the unique commits
        # TODO : stop when we hit a SHA we've already imported
        while todo:
            sha = todo.pop()
            assert isinstance(sha, str)
            if sha in done:
                continue
            done.add(sha)
            commit = self.git.commit(sha)
            convert_list.append(commit)
            todo.extend([p for p in commit.parents if p not in done])
        
        # sort the commits by commit date (TODO: change to topo sort)
        convert_list.sort(cmp=lambda x,y: x.commit_time-y.commit_time)
        
        # import each of the commits, oldest first
        for commit in convert_list:
            print "commit: %s" % sha
            self.import_git_commit(commit)
    
        # TODO : update Hg bookmarks (possibly named heads?)
        print bookmarks.parse(self.repo)

    def import_git_commit(self, commit):
        # check that parents are all in Hg, or no parents
        print commit.parents

        def getfilectx(repo, memctx, f):
            data = commit.getfile(f)
            e = commit.getmode(f)
            return context.memfilectx(f, data, 'l' in e, 'x' in e, None)
            
        p1 = "0" * 40
        p2 = "0" * 40

        files = ['test']

        # get a list of the changed, added, removed files
        text = commit.message
        extra = {}
        date = datetime.datetime.fromtimestamp(commit.author_time).strftime("%Y-%m-%d")
        print date
        ctx = context.memctx(self.repo, (p1, p2), text, files, getfilectx,
                             commit.author, date, extra)
        print ctx
        a = self.repo.commitctx(ctx)
        print a
        #puts p2 = hex(self.repo.changelog.tip())
        
        pass
        
    def getfilectx(self, source, repo, memctx, f):
        v = files[f]
        data = source.getfile(f, v)
        e = source.getmode(f, v)
        return context.memfilectx(f, data, 'l' in e, 'x' in e, copies.get(f))

    def export_git_objects(self):
        pass

    def check_bookmarks(self):
        if self.ui.config('extensions', 'hgext.bookmarks') is not None:
            print "YOU NEED TO SETUP BOOKMARKS"

    def get_transport_and_path(self, uri):
        from dulwich.client import TCPGitClient, SSHGitClient, SubprocessGitClient
        for handler, transport in (("git://", TCPGitClient), ("git+ssh://", SSHGitClient)):
            if uri.startswith(handler):
                host, path = uri[len(handler):].split("/", 1)
                return transport(host), "/"+path
        # if its not git or git+ssh, try a local url..
        return SubprocessGitClient(), uri

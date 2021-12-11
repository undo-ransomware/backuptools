# parser for rsync command line as it appears in SSH_ORIGINAL_COMMAND
# (ie. as a space delimited string, with no escaping, quoting etc.)
from collections import defaultdict
import re

class RsyncParser:
	def __init__(self):
		self.restore = dict()
		self.backup = dict()
		self.verify = dict()
		self.list = dict()

	def is_quiet(self):
		return '-q' in self.opts or '--quiet' in self.opts

	def is_verbose(self):
		return '-v' in self.opts or '--verbose' in self.opts

	def get_mode(self):
		return self.mode

	def get_messages(self):
		msgs = list()
		for name, msglist in [('ERROR', self._error), ('WARNING', self._warn)]:
			for opt, (msg, hint) in sorted(msglist.items()):
				if hint is not None:
					msgs.append('%s %s %s (%s)' % (name, msg, opt, hint))
				else:
					msgs.append('%s %s %s' % (name, msg, opt))
		return msgs

	def get_command(self):
		if len(self._error) > 0:
			return None
		cmd = ['rsync', '--server']
		for opt, values in sorted(self.opts.items()):
			for value in sorted(values):
				if value is not None:
					cmd.append('%s%s' % (opt, value))
				else:
					cmd.append(opt)
		return cmd

	def get_path(self):
		if len(self._error) > 0:
			return None
		return self.path

	def warn(self, opt, msg, hint=None):
		self._warn[opt] = (msg, hint)

	def error(self, opt, msg, hint=None):
		self._error[opt] = (msg, hint)

	def parse(self, cmdline):
		self._warn = dict()
		self._error = dict()
		self.opts = defaultdict(list)

		if not cmdline.startswith('rsync --server '):
			raise RsyncParserException('shell access not allowed, use rsync')

		opts = cmdline[15:]
		while opts.startswith('-'):
			if opts.startswith('--'):
				opt, opts = opts.split(' ', 1)
				if '=' in opt: # rsync always passes them as --option=value
					opt, value = opt.split('=', 1)
					opt += '='
				else:
					value = None
			elif opts.startswith('-e'): # special case, -e takes specifies a few internal feature flags
				value, opts = opts.split(' ', 1)
				m = re.match('-e\d*\.\d*(i?).*', value)
				if not m:
					self.error('-e', 'strange -e options string %s' % value)
				else:
					self.inc_rec = m.group(1) == 'i'
				self.opts[value].append(None)
				continue
			elif opts.startswith('- '): # last short option parsed
				opts = opts[2:]
				continue
			else:
				opt = opts[:2]
				value = None
				opts = '-' + opts[2:]

			if opt not in ['--sender', '--list-only', '-q', '--quiet', '-v', '--verbose', '-n', '--dry-run'] \
					and opt not in self.restore: # member set is identical for all of them!
				self.error(opt, 'unknown option')
				continue
			self.opts[opt].append(value)

		if not opts.startswith('. '):
			raise RsyncParserException('rsync --server must give source as ".", but found %s' % opts)
		self.path = opts[2:]

		if '--list-only' in self.opts: # --list-only overrides (implies?) -n
			optlist = self.list
			self.mode = 'list'
		elif '-n' in self.opts or '--dry-run' in self.opts:
			optlist = self.verify
			self.mode = 'verify'
		elif '--sender' in self.opts:
			optlist = self.restore
			self.mode = 'restore'
		else:
			optlist = self.backup
			self.mode = 'backup'
		for opt, (mode, hard, alias, hint) in optlist.items():
			key = opt if alias is None else alias
			if mode == 'require' and opt not in self.opts:
				if hard:
					self.error(key, 'must use', hint)
				else:
					self.warn(key, 'consider using', hint)
			if mode == 'deny' and opt in self.opts:
				if hard:
					self.error(key, 'do not use', hint)
				else:
					self.warn(key, 'avoid using', hint)
		if not self.inc_rec and '-r' in self.opts:
			self.warn('--inc-recursive', 'incremental recursion not enabled, consider using')

	def add(self, modes, *args, alias=None):
		for names, mode, *hint in modes:
			if names is None:
				names = 'restore backup verify list'
			hint = hint[0] if len(hint) > 0 else None

			for name in names.split(' '):
				if mode == 'discourage':
					mode = 'deny'
					hard = False
				elif mode == 'recommend':
					mode = 'require'
					hard = False
				else:
					hard = True
				if mode not in ['allow', 'deny', 'require']:
					raise RsyncParserException('illegal %s mode %s' % (name, mode))

				arglist = { 'restore': self.restore, 'backup': self.backup, 'verify': self.verify,
						'list': self.list }[name]
				for arg in args:
					local_alias = arg if alias is None else alias
					local_alias = ' / '.join(local_alias.split(' ', 1))
					if ' ' in arg:
						arg = arg.split(' ', 1)[0]
					arglist[arg] = (mode, hard, local_alias, hint)

	def allow(self, *args, hint=None, **kwargs):
		self.add([(None, 'allow', hint)], *args, **kwargs)
	def deny(self, *args, hint=None, **kwargs):
		self.add([(None, 'deny', hint)], *args, **kwargs)
	def require(self, *args, hint=None, **kwargs):
		self.add([(None, 'require', hint)], *args, **kwargs)
	def discourage(self, *args, hint=None, **kwargs):
		self.add([(None, 'discourage', hint)], *args, **kwargs)
	def recommend(self, *args, hint=None, **kwargs):
		self.add([(None, 'recommend', hint)], *args, **kwargs)

class RsyncParserException(Exception):
	pass

if __name__ == '__main__':
	parser = RsyncParser()
	parser.require('-r', '-l', '-p', '-t', '-g', '-o', '-D', alias='-a --alias')

	try:
		parser.parse('rm -rf /')
		assert not 'missing exception';
	except RsyncParserException:
		pass
	try:
		parser.parse('')
		assert not 'missing exception';
	except RsyncParserException:
		pass
	try:
		parser.parse('rsync /etc/passwd /home/attacker/passwd')
		assert not 'missing exception';
	except RsyncParserException:
		pass
	try:
		parser.parse('rsync --server --sender -vlogDtprze.iLsfxC foo bar')
		assert not 'missing exception';
	except RsyncParserException:
		pass

	parser.parse('rsync --server --sender -vlogtprze.iLsfxC . root/test')
	assert parser.get_messages() == ['ERROR must use -a / --alias', 'ERROR unknown option -z']
	assert parser.get_path() is None
	assert parser.get_command() is None

	parser.allow('-z --checksum')
	parser.discourage('-C')
	parser.recommend('--numeric-ids')
	parser.parse('rsync --server --sender -vClogDtprze.iLsfxC . root/test')
	assert parser.get_messages() == ['WARNING consider using --numeric-ids', 'WARNING avoid using -C']
	assert parser.get_path() == 'root/test'
	assert parser.get_command() == ['rsync', '--server', '--sender', '-C', '-D', '-e.iLsfxC', '-g', '-l', '-o', '-p',
			'-r', '-t', '-v', '-z']
	assert parser.is_verbose()
	assert not parser.is_quiet()
	assert parser.get_mode() == 'restore'

	parser.parse('rsync --server -qrlptgoDe.iLsfxC --numeric-ids . root  and other stuff&/$nothing')
	assert parser.get_messages() == []
	assert parser.get_path() == 'root  and other stuff&/$nothing'
	assert parser.get_command() == ['rsync', '--server', '--numeric-ids', '-D', '-e.iLsfxC', '-g', '-l', '-o', '-p',
			'-q', '-r', '-t']
	assert not parser.is_verbose()
	assert parser.is_quiet()
	assert parser.get_mode() == 'backup'

	parser.parse('rsync --server --list-only -rlptgoDe.iLsfxC --numeric-ids . root@2011-01-01/etc/passwd ')
	assert parser.get_messages() == []
	assert parser.get_path() == 'root@2011-01-01/etc/passwd '
	assert parser.get_command() == ['rsync', '--server', '--list-only', '--numeric-ids', '-D', '-e.iLsfxC', '-g', '-l',
		'-o', '-p', '-r', '-t']
	assert not parser.is_verbose()
	assert not parser.is_quiet()
	assert parser.get_mode() == 'list'

	parser.parse('rsync --server -nzrlptgoDe.iLsfxC --numeric-ids . /')
	assert parser.get_messages() == []
	assert parser.get_path() == '/'
	assert parser.get_command() == ['rsync', '--server', '--numeric-ids', '-D', '-e.iLsfxC', '-g', '-l', '-n', '-o',
			'-p', '-r', '-t', '-z']
	assert not parser.is_verbose()
	assert not parser.is_quiet()
	assert parser.get_mode() == 'verify'

	parser.add([('backup', 'allow'), ('restore verify list', 'deny', 'ever')], '--list=', '--unlist')
	parser.add([('restore', 'allow'), ('backup verify list', 'discourage')], '--lost=')
	parser.parse('rsync --server -zrlptgoDe.iLsfxC --numeric-ids --list=nothing --lost=/dev/null . /')
	assert parser.get_messages() == ['WARNING avoid using --lost=']
	assert parser.get_path() == '/'
	assert parser.get_command() == ['rsync', '--server', '--list=nothing', '--lost=/dev/null', '--numeric-ids', '-D',
			'-e.iLsfxC', '-g', '-l', '-o', '-p', '-r', '-t', '-z']
	assert not parser.is_verbose()
	assert not parser.is_quiet()
	assert parser.get_mode() == 'backup'

	parser.parse('rsync --server --sender -zrlptgoDe.iLsfxC --numeric-ids --list=nothing --lost --lost=/dev/null . /')
	assert parser.get_messages() == ['ERROR do not use --list= (ever)', 'ERROR unknown option --lost']
	assert parser.get_path() is None
	assert parser.get_command() is None
	assert not parser.is_verbose()
	assert not parser.is_quiet()
	assert parser.get_mode() == 'restore'

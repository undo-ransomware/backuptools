# parser for rsync command line as it appears in SSH_ORIGINAL_COMMAND
# (ie. as a space delimited string, with no escaping, quoting etc.)
from collections import defaultdict
import re

class RsyncParser:
	def __init__(self):
		self.required = dict()

	def is_quiet(self):
		return '-q' in self.opts or '--quiet' in self.opts

	def is_verbose(self):
		return '-v' in self.opts or '--verbose' in self.opts

	def is_sender(self):
		return '--sender' in self.opts

	def is_list(self):
		return '--list-only' in self.opts

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
					cmd.append('%s=%s' % (opt, value))
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
				else:
					value = None
			elif opts.startswith('-e'): # special case, -e takes specifies a few internal feature flags
				value, opts = opts.split(' ', 1)
				m = re.match('-e\d*\.\d*(i?).*', value)
				if not m:
					self.error('-e', 'strange -e options string %s' % value)
				elif m.group(1) != 'i':
					self.warn('--inc-recursive', 'incremental recursion not enabled, consider using')
				self.opts[value].append(None)
				continue
			elif opts.startswith('- '): # last short option parsed
				opts = opts[2:]
				continue
			else:
				opt = opts[:2]
				value = None
				opts = '-' + opts[2:]

			if opt in ['--sender', '--list-only', '-q', '--quiet', '-v', '--verbose']: # special options
				self.opts[opt].append(value)
				continue
			if opt not in self.required:
				self.error(opt, 'unknown option')
				continue
			method, hard, alias, hint = self.required[opt]
			key = opt if alias is None else alias
			if method == 'deny':
				if hard:
					self.error(key, 'do not use', hint)
				else:
					self.warn(key, 'avoid using', hint)
					self.opts[opt].append(value)
			else: # allow or require
				self.opts[opt].append(value)

		for opt, (method, hard, alias, hint) in self.required.items():
			if method == 'require' and opt not in self.opts:
				key = opt if alias is None else alias
				if hard:
					self.error(key, 'must use', hint)
				else:
					self.warn(key, 'consider using', hint)

		if not opts.startswith('. '):
			raise RsyncParserException('rsync --server must give source as "." not as in %s' % opts)
		self.path = opts[2:]

	def add_argument(self, *args, method='allow', hard=True, alias=None, hint=None):
		if method not in ['allow', 'deny', 'require']:
			raise RsyncParserException('illegal method %s' % method)
		for arg in args:
			if ' ' in arg:
				arg, local_alias = arg.split(' ', 1)
			else:
				local_alias = alias
			if local_alias is not None and ' ' in local_alias:
				short, long = local_alias.split(' ', 1)
				local_alias = '%s / %s' % (short, long)
			self.required[arg] = (method, hard, local_alias, hint)

	def allow(self, *arg, **kwargs):
		self.add_argument(*arg, method='allow', **kwargs)
	def deny(self, *arg, **kwargs):
		self.add_argument(*arg, method='deny', **kwargs)
	def require(self, *arg, **kwargs):
		self.add_argument(*arg, method='require', **kwargs)
	def discourage(self, *arg, **kwargs):
		self.add_argument(*arg, method='deny', hard=False, **kwargs)
	def recommend(self, *arg, **kwargs):
		self.add_argument(*arg, method='require', hard=False, **kwargs)

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
	assert parser.is_sender()
	assert not parser.is_list()

	parser.parse('rsync --server -qrlptgoDe.iLsfxC --numeric-ids . root  and other stuff&/$nothing')
	assert parser.get_messages() == []
	assert parser.get_path() == 'root  and other stuff&/$nothing'
	assert parser.get_command() == ['rsync', '--server', '--numeric-ids', '-D', '-e.iLsfxC', '-g', '-l', '-o', '-p',
			'-q', '-r', '-t']
	assert not parser.is_verbose()
	assert parser.is_quiet()
	assert not parser.is_sender()
	assert not parser.is_list()

	parser.parse('rsync --server --list-only -rlptgoDe.iLsfxC --numeric-ids . root@2011-01-01/etc/passwd ')
	assert parser.get_messages() == []
	assert parser.get_path() == 'root@2011-01-01/etc/passwd '
	assert parser.get_command() == ['rsync', '--server', '--list-only', '--numeric-ids', '-D', '-e.iLsfxC', '-g', '-l',
		'-o', '-p', '-r', '-t']
	assert not parser.is_verbose()
	assert not parser.is_quiet()
	assert not parser.is_sender()
	assert parser.is_list()

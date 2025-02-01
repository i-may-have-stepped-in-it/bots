async def teamviewer(config,message):
	import pexpect
	# Create a Pexpect object for the SSH connection
	ssh_conn = pexpect.spawn('ssh bot@192.168.128.134')
	if ssh_conn.expect('yes/no/fingerprint:'):
		ssh_conn.sendline('yes')

	# Expect the SSH password prompt
	if ssh_conn.expect('password:'):
		# Send the SSH password
		ssh_conn.sendline('password')

	# Expect the SSH command prompt
	ssh_conn.expect('[$#]')

	# Send the command to run the update.sh script
	ssh_conn.sendline('sudo /usr/local/bin/teamviewer.sh')
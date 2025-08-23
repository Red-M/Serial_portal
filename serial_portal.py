#!/usr/bin/env python3
import os
import sys
import random
import time
import traceback
import subprocess
import yaml

import redssh
import redexpect
import ssh2

redssh.clients.default_client = 'LibSSH2'

DEBUG = True
# DEBUG = False
current_dir = os.getcwd()


class localRedExpect(redexpect.RedExpect):
    def __init__(self,**kwargs):
        # super().__init__(terminal='xterm',**kwargs)
        super().__init__(**kwargs)
        # self.basic_prompt = r'[\$\#]'
        self.basic_prompt = self.get_unique_prompt()
        self.prompt_regex = self.basic_prompt

        self.set_flags = {redssh.libssh2.LIBSSH2_FLAG_COMPRESS: True}

    def send_tmux_command(self,cmd):
        self.sendline_raw('\002')
        self.sendline_raw(cmd)

    def get_unique_prompt(self):
        return(r'C.+?\[.+?\:.+?\].+?\@.+?([\#\$]\s+|[\#\$])')


class serialDevice:
    def __init__(self,parent,device,config):
        self.device = device
        self.config = config
        self.parent = parent
        self.remote_serial_port = random.randrange(23000,24000,1)
        self.remote_command = ''
        self.local_port = 0
        self.local_command = []
        self.local_process = None
        self.remote_pid = None

        self.remote_side()

    def remote_side(self):
        self.remote_command = 'socat FILE:'+self.device+',b'+str(self.config['baudrate'])+','+self.config.get('options',{}).get('remote','')+' TCP4-LISTEN:'+str(self.remote_serial_port)+',bind=127.0.0.1,keepalive,nodelay,reuseaddr,keepidle=1,keepintvl=1,keepcnt=5,fork &'

    def local_side(self):
        self.local_port = self.parent.ssh.local_tunnel(0,'127.0.0.1',self.remote_serial_port,error_level=redssh.enums.TunnelErrorLevel.debug)
        local_command = ['socat', '-v', 'TCP:127.0.0.1:'+str(self.local_port)+',keepalive,nodelay,keepidle=1,keepintvl=1,keepcnt=5']

        if self.config['mode'] == 'tcp':
            local_command.append('TCP-LISTEN:'+str(self.config['port'])+','+self.config.get('options',{}).get('local',''))
        if self.config['mode'] == 'pty':
            local_command.append('PTY,link='+self.config['path']+','+self.config.get('options',{}).get('local',''))

        if DEBUG == False:
            local_command.pop(1)

        self.local_command = local_command
        self.local_process = subprocess.Popen(self.local_command)
        print(self.device+': ready!')

    def poll(self):
        poll = False
        try:
            self.local_process.poll()
            if self.parent.ssh.tunnel_is_alive(redssh.enums.TunnelType.local,self.local_port,'127.0.0.1',self.remote_serial_port)==False:
                pass
            poll = True
        except Exception as e:
            if not isinstance(e,type(KeyboardInterrupt)):
                if DEBUG==True:
                    traceback.print_exception(*sys.exc_info())
                    print('-'*80)
                else:
                    print(e)
                time.sleep(1)
            else:
                pass
        return(poll)


class session:
    def __init__(self,parent,name,config):
        self.name = name
        self.config = config
        self.parent = parent

        self.serial_devices = []
        for serial_path in self.config['serial_devices']:
            self.serial_devices.append(serialDevice(self,serial_path,self.config['serial_devices'][serial_path]))

        self.key_file = os.path.join(current_dir,self.config['key_file'])
        self.ssh = localRedExpect(ssh_keepalive_interval=1.0,expect_timeout=0,auto_terminate_tunnels=True,tcp_nodelay=True)
        self.ssh.set_flags = {redssh.libssh2.LIBSSH2_FLAG_COMPRESS: True}
        print('Connecting...')
        self.ssh.login(hostname=self.config['host'],username=self.config['user'],key_filepath=self.key_file,timeout=30,allow_agent=False)
        print('Connected!')
        self.ssh.command('unset HISTFILE')

        for serial_device in self.serial_devices:
            self.ssh.command(serial_device.remote_command,remove_newline=True)
            serial_device.local_side()

    def poll(self):
        poll = True
        for serial_device in self.serial_devices:
            polled = serial_device.poll()
            if polled==False:
                poll = polled
                break
        return(poll)

    def exit(self):
        self.ssh.close_tunnels()
        self.ssh.exit()


class serialPortal:

    def __init__(self):
        self.sessions = {}
        self.load_config()

        for session_name in self.config['sessions']:
            self.sessions[session_name] = session(self,session_name,self.config['sessions'][session_name])

        self.handle_sessions()

    def load_config(self):
        f = open(os.path.join(current_dir, 'config.yaml'), 'r')
        self.config = yaml.load(f,Loader=yaml.FullLoader)
        f.close()

        # deletes config keys for sessions or serial devices that have enable == False
        enable_key = 'enable'
        session_keys = list(self.config['sessions'].keys())
        for sess in session_keys:
            if self.config['sessions'][sess].get(enable_key, True)==False:
                del self.config['sessions'][sess]
            else:
                serial_keys = list(self.config['sessions'][sess]['serial_devices'].keys())
                for serial in serial_keys:
                    if self.config['sessions'][sess]['serial_devices'][serial].get(enable_key, True)==False:
                        del self.config['sessions'][sess]['serial_devices'][serial]

    def handle_sessions(self):
        try:
            poll = True
            while poll==True:
                time.sleep(0.1)
                for sess in self.sessions:
                    polled = self.sessions[sess].poll()
                    if polled==False:
                        poll = polled
                        break
        except Exception as e:
            if not isinstance(e,type(KeyboardInterrupt)):
                if DEBUG==True:
                    traceback.print_exception(*sys.exc_info())
                    print('-'*80)
                else:
                    print(e)
                time.sleep(1)
            else:
                pass
        finally:
            for sess in self.sessions:
                self.sessions[sess].exit()



if __name__ == '__main__':
    serialPortal()


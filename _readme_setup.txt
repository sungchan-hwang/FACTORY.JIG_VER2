0. upstart ��ġ. (��ġ�ϸ� ���� �ȵ�.)
	apt-get install upstart

--------------------------------------------
	
1. apt-get upgrade
   apt-get update
   	
2. samba ��ġ.
	apt-get install samba samba-common-bin
	
3. requests ��ġ.
	pip3 install requests
	
4. flask ��ġ.
	pip3 install flask
	
5. RPi.GPIO ��ġ.
	pip3 install RPi.GPIO
	
6. pyserial ��ġ.
	pip3 install pyserial
		
7. dhcp disable
	systemctl disable dhcpcd.service
	systemctl enable networking
	reboot
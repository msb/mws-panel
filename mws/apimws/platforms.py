import json
import os
import random
import string
import crypt
from django.conf import settings
import requests
import platform
from sitesmanagement.models import VirtualMachine, NetworkConfig


class PlatformsAPINotWorkingException(Exception):
    pass

class PlatformsAPIInputException(Exception):
    pass

class NoPrealocatedPrivateIPsAvailable(Exception):
    pass


def get_api_secret():
    if platform.system() == 'Darwin':
        from passlib.hash import sha512_crypt
        return sha512_crypt.encrypt(settings.PLATFORMS_API_TOKEN, rounds=5000,
                                    implicit_rounds=True)  # Salt autogenerated
    return crypt.crypt(settings.PLATFORMS_API_TOKEN, "$6$"+''.join(random.sample(string.hexdigits, 16)))


def get_api_username():
    return settings.PLATFORMS_API_USERNAME


def new_site_primary_vm(vm):
    json_object = {
        'username': get_api_username(),
        'secret': get_api_secret(),
        'command': 'create',
        'ip': vm.network_configuration.IPv4,
        'hostname': vm.network_configuration.mws_domain,
    }
    headers = {'Content-type': 'application/json'}
    try:
        response = json.loads(requests.post("https://bes.csi.cam.ac.uk/mws-api/v1/vm.json",
                                            data=json.dumps(json_object), headers=headers).text)
    except Exception as e:
        raise PlatformsAPINotWorkingException(e.message)  # TODO capture exception where it is called

    if response['result'] == 'Success':
        vm.name = response['vmid']
        vm.status = 'ready'
        vm.save()
        return install_vm(vm)
    else:
        return False  # TODO raise error


def install_vm(vm):
    f = open(os.path.join(settings.BASE_DIR, 'apimws/ubuntu_preseed.txt'), 'r')
    profile = f.read()
    f.close()

    json_object = {
        'username': get_api_username(),
        'secret': get_api_secret(),
        'command': 'install',
        'vmid': vm.name,
        'profile': profile,
    }
    headers = {'Content-type': 'application/json'}
    try:
        response = json.loads(requests.post("https://bes.csi.cam.ac.uk/mws-api/v1/vm.json",
                                            data=json.dumps(json_object), headers=headers).text)
    except Exception as e:
        raise PlatformsAPINotWorkingException(e.message)  # TODO capture exception where it is called

    if response['result'] == 'Success':
        return True
    else:
        return False  # TODO raise error


def get_vm_power_state(vm):
    json_object = {
        'username': get_api_username(),
        'secret': get_api_secret(),
        'command': 'get power state',
        'vmid': vm.name
    }
    headers = {'Content-type': 'application/json'}
    try:
        response = json.loads(requests.post("https://bes.csi.cam.ac.uk/mws-api/v1/vm.json",
                                            data=json.dumps(json_object), headers=headers).text)
    except Exception as e:
        raise PlatformsAPINotWorkingException(e.message)

    if response['result'] == 'Success':
        if response['powerState'] == 'poweredOff':
            return "Off"
        elif response['powerState'] == 'poweredOn':
            return "On"
        else:
            pass  # TODO raise error
    else:
        pass  # TODO raise error


def change_vm_power_state(vm, on):
    if on != 'on' and on != 'off':
        raise PlatformsAPIInputException("passed wrong parameter power %s" % on)

    json_object = {
        'username': get_api_username(),
        'secret': get_api_secret(),
        'command': 'power '+on,
        'vmid': vm.name
    }

    headers = {'Content-type': 'application/json'}
    try:
        response = json.loads(requests.post("https://bes.csi.cam.ac.uk/mws-api/v1/vm.json",
                                            data=json.dumps(json_object), headers=headers).text)
    except Exception as e:
        raise PlatformsAPINotWorkingException(e.message)  # TODO capture exception where it is called

    if response['result'] == 'Success':
        return True
    else:
        return False  # TODO raise error


def reset_vm(vm):
    json_object = {
        'username': get_api_username(),
        'secret': get_api_secret(),
        'command': 'reset',
        'vmid': vm.name
    }

    headers = {'Content-type': 'application/json'}
    r = requests.post("https://bes.csi.cam.ac.uk/mws-api/v1/vm.json", data=json.dumps(json_object), headers=headers)
    try:
        response = json.loads(r.text)
    except Exception as e:
        raise PlatformsAPINotWorkingException(e.message)  # TODO capture exception where it is called

    if response['result'] == 'Success':
        return True
    else:
        return False # TODO raise error


def destroy_vm(vm):
    change_vm_power_state(vm, "off")

    json_object = {
        'username': get_api_username(),
        'secret': get_api_secret(),
        'command': 'destroy',
        'vmid': vm.name
    }

    headers = {'Content-type': 'application/json'}
    r = requests.post("https://bes.csi.cam.ac.uk/mws-api/v1/vm.json", data=json.dumps(json_object), headers=headers)
    try:
        response = json.loads(r.text)
    except Exception as e:
        raise PlatformsAPINotWorkingException(e.message)  # TODO capture exception where it is called

    if response['result'] == 'Success':
        return True
    else:
        raise PlatformsAPINotWorkingException()  # TODO capture exception where it is called


def clone_vm(site, primary_vm):
    if primary_vm:
        orignal_vm = site.primary_vm
        if site.secondary_vm:
            network_configuration = site.secondary_vm.network_configuration
            site.secondary_vm.delete()
        else:
            network_configuration = NetworkConfig.get_free_private_ip()
    else:
        orignal_vm = site.secondary_vm
        if site.primary_vm:
            network_configuration = site.primary_vm.network_configuration
            site.primary_vm.delete()
        else:
            network_configuration = NetworkConfig.get_free_public_ip()

    if network_configuration is None:
        raise NoPrealocatedPrivateIPsAvailable()

    destiantion_vm = VirtualMachine.objects.create(primary=(not primary_vm), status='requested',
                                                   network_configuration=network_configuration, site=site)
    clone_vm_api_call.delay(orignal_vm, destiantion_vm)


def clone_vm_api_call(orignal_vm, destiantion_vm):
    json_object = {
        'username': get_api_username(),
        'secret': get_api_secret(),
        'command': 'clone',
        'vmid': orignal_vm.name,
        'ip': destiantion_vm.network_configuration.IPv4,
        'hostname': destiantion_vm.network_configuration.mws_domain,
    }
    headers = {'Content-type': 'application/json'}
    try:
        response = json.loads(requests.post("https://bes.csi.cam.ac.uk/mws-api/v1/vm.json",
                                            data=json.dumps(json_object), headers=headers).text)
    except Exception as e:
        raise PlatformsAPINotWorkingException(e.message)  # TODO capture exception where it is called

    if response['result'] == 'Success':
        destiantion_vm.name = response['vmid']
        destiantion_vm.status = 'ready'
        destiantion_vm.save()
        return True
    else:
        return False  # TODO raise error
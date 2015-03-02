from __future__ import absolute_import
import logging
import uuid
from celery import shared_task, Task
import json
from django.core.urlresolvers import reverse
import os
import random
import string
import crypt
from django.conf import settings
import requests
import platform
from sitesmanagement.models import VirtualMachine, NetworkConfig


LOGGER = logging.getLogger('mws')


class PlatformsAPINotWorkingException(Exception):
    pass


class PlatformsAPIInputException(Exception):
    pass


class PlatformsAPIFailure(Exception):
    pass


def get_api_secret():
    if platform.system() == 'Darwin':
        from passlib.hash import sha512_crypt
        return sha512_crypt.encrypt(settings.PLATFORMS_API_TOKEN, rounds=5000,
                                    implicit_rounds=True)  # Salt autogenerated
    return crypt.crypt(settings.PLATFORMS_API_TOKEN, "$6$"+''.join(random.sample(string.hexdigits, 16)))


def get_api_username():
    return settings.PLATFORMS_API_USERNAME


def vm_api_request(**json_object):
    headers = {'Content-type': 'application/json'}
    json_object['username'] = get_api_username()
    json_object['secret'] = get_api_secret()
    vm_api_url = "https://bes.csi.cam.ac.uk/mws-api/v1/vm.json"
    response = json.loads(requests.post(vm_api_url, data=json.dumps(json_object), headers=headers).text)
    LOGGER.info("VM API request: %s\nVM API response: %s", json_object, response)
    if response['result'] != 'Success':
        raise PlatformsAPIFailure(json_object, response)
    return response


def on_vm_api_failure(request, response):
    ''' This function logs the error in the logger. The logger can be configured to send an email.
    :param request: the VM API request
    :param response: the VM API response
    :return: False
    '''
    LOGGER.error("VM API request: %s\nVM API response: %s", request, response)
    return False  # TODO raise exception?


class TaskWithFailure(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        LOGGER.error("An error happened when trying to communicate with Platform's VM API.\n The task id is %s. \n\n "
                     "The parameters passed to the task were: %s \n\n The traceback is: \n %s", task_id, args, einfo)
        # TODO raise exception?


@shared_task(base=TaskWithFailure, default_retry_delay=5*60, max_retries=288)  # Retry each 5 minutes for 24 hours
def new_site_primary_vm(vm):
    json_object = {}
    if settings.OS_VERSION_VMAPI:
        json_object['os'] = settings.OS_VERSION_VMAPI

    try:
        response = vm_api_request(command='create', ip=vm.ipv4, hostname=vm.hostname, **json_object)
    except PlatformsAPIFailure as e:
        return on_vm_api_failure(*e.args)
    except Exception as e:
        raise new_site_primary_vm.retry(exc=e)

    vm.name = response['vmid']
    vm.status = 'installing'
    vm.save()
    return install_vm(vm)


@shared_task(base=TaskWithFailure, default_retry_delay=5*60, max_retries=288)  # Retry each 5 minutes for 24 hours
def install_vm(vm):
    from apimws.models import AnsibleConfiguration
    AnsibleConfiguration.objects.update_or_create(vm=vm, key='os', defaults={'value': json.dumps(settings.OS_VERSION)})

    f = open(os.path.join(settings.BASE_DIR, 'apimws/debian_preseed.txt'), 'r')
    profile = f.read()
    f.close()

    from apimws.views import post_installation
    late_commands = [
        "mkdir -p /target/root/.ssh",
        "echo 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC6H3DRdUPejq6JRLBFNG4S0y/vqrTVQZBQMLeMcMjCctgpdkXF54/6yzmVOtsqoaeC"
        "KQZhlFWbP1CnBVBAnU6nZU7zlh7flMT3RfxkCCOmE7Pg85EaY04R2rKymPsUGaN94J7mzNBN9NP+UuCtWfPHQ5jW/FJvfTDimcjAvuvnSIrlce"
        "tSlAam6lmbdj660TOeSoWJD0myWu9BaRGNrjpRellNuomk00YvHkSBYjo0zRY1FHg/x1wie/mNnVEW7AvELYhe/+u3PRYzKaZcQ07ETfCdtwBg"
        "WTI+GvNkAnYSFTUd0nvYdkhCmA81KpwKwlctm4BXgA7tMr2ZBLGpcg3R mcv21@pick' >/target/root/.ssh/authorized_keys",

        "echo 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCerKj8UJ4F6njySBpvRJWnH2A5KQopP+DO8aiRGeQkRmCCorKdmX8q79anpWmQkuxd"
        "qEXlCOEezOToFC992akTolkjCT0VPYWd5ZuIvvzwwe66vmqMXN1m7wfFHgtLAqDkF+KK94mQnmAh8HGL5WL3BGl+w8VaXxnfIUYpuzYdf0CZ3m"
        "ET1lYNAal9cU4R4D1FBflmxSIWJKwrMrfHiXo+YIwyQvH21ZNAeEvEV4E9EgwkF1HjkVs7KUCxwjya652xbJWxQMcxflK8T0TY9fq6GWbbWatW"
        "Y6J40wN7dqp+WgWjGyOrqDc3AUeJ37/sSqmJ7B/SBemPNId27I3EbJ1V bjh21@wraith' >>/target/root/.ssh/authorized_keys",

        "echo 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDY8qT0ucAal95O6XpDq7uhNT+Fal3q+DPB2wBiUXtSjgCuWZFYeoKkR7rq97MM/tCy"
        "aW4ItCfWH1QTLsx1FOOTyfMiM9vDqpFJuDVzI/5pwOJVZYu27zxeWc1Dqa+ReabwqizL2kCxtvCx9bwRbUTFnfhXxb9y4bEHmkBHfp59Z6zJHr"
        "5/OTDsBioFUQkcQucpJB+fD0QRxCqk5xDIaiFI/xEVr4WhRkj7CWX4IYAn/gvOgNTrcunseYeIKC7V/9SB5bbKfFMMiJz8PW3bOJp5kDPZ4RA+"
        "AiVHguQ2geniryfsxlM78AHkQJ5b7arx7KgAFWR+kh5+9c32NQbPpj/D amc203' >>/target/root/.ssh/authorized_keys",

        "echo 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDAZURi9pqzIO/u92JSBdAKAfQAgEqCNBydHKvsMOQa9IdMxyjNP83ubO+KxQ7RLEF2"
        "BFUmCeFPG6tz+ZQY9tgaRIfiujCf8+rr2Seg5vDPlHOJFF0WZYEDUgf+KwrXfv8d3DfSgX77A/IGYNHfL6ASar64XbUBpXA/AuldEqDfRAYM+Y"
        "yK7dD50kc7fH+sM2izeF6NmNQFvewkNqbov2j26knzcG4yBMRLrviUmniSwyfv/HIoj/nM/nV7TUgguCSgzvyU9C1dR+LRuc1YbcvxUkX7Ff9/"
        "cJ9TRsWaPERk+/hWQb0TiiWLLM7F5n6X6lyv+CVZtsz7N+PgVNa83tRDPog8lDc6jYkIFA2G7u6dZi/TbrAxL3CfkMqhl0AL5a56eELQLs/wIH"
        "BDqPfZzvUEXe07m/HrxN0lJCY9GiIHk/xKStL4XqMgCY/yu6gBGe4u0tM9xa/SNEbd0B+DHGzEabGpyRu6n9k9ULAfZMZoUnRswUZFpml2VICw"
        "5JaFzPuJI8Gh9RMDBBp4grAtGG2/a2pvNh8Lr5qCXlpbraCM/NboVLwJl+021V5Sgzh0BALssMcLzoJHcck0D7Paou2QatpIMVm/hWNiVJ5qoF"
        "1zjDdHRKAzMKP+hdiagrR1s+ns2FQ6tTW5bfyrUm3j5RoYh8TyXPh9G2t5+GhaPRxZtw== mws-admin superuser key' "
        ">>/target/root/.ssh/authorized_keys",

        '{ curl --data "vm=%s&token=%s" %s%s || true; }' %
        (vm.id, vm.token, settings.MAIN_DOMAIN, reverse(post_installation))
    ]

    profile += ('\nd-i preseed/late_command string %s' %
                (" && ".join(late_commands),))

    try:
        vm_api_request(command='install', vmid=vm.name, profile=profile)
    except PlatformsAPIFailure as e:
        return on_vm_api_failure(*e.args)
    except Exception as e:
        raise install_vm.retry(exc=e)

    return True


def get_vm_power_state(vm):
    try:
        response = vm_api_request(command='get power state', vmid=vm.name)
    except PlatformsAPIFailure:
        raise
    except Exception as e:
        raise PlatformsAPINotWorkingException(e.message)

    if response['powerState'] == 'poweredOff':
        return "Off"
    elif response['powerState'] == 'poweredOn':
        return "On"
    else:
        raise PlatformsAPIFailure(None, response)


@shared_task(base=TaskWithFailure, default_retry_delay=5*60, max_retries=288)  # Retry each 5 minutes for 24 hours
def change_vm_power_state(vm, on):
    if on != 'on' and on != 'off':
        raise PlatformsAPIInputException("passed wrong parameter power %s" % on)
    try:
        vm_api_request(command='power ' + on, vmid=vm.name)
    except PlatformsAPIFailure as e:
        return on_vm_api_failure(*e.args)
    except Exception as e:
        raise change_vm_power_state.retry(exc=e)

    return True


@shared_task(base=TaskWithFailure, default_retry_delay=5*60, max_retries=288)  # Retry each 5 minutes for 24 hours
def reset_vm(vm):
    try:
        vm_api_request(command='reset', vmid=vm.name)
    except PlatformsAPIFailure as e:
        return on_vm_api_failure(*e.args)
    except Exception as e:
        raise reset_vm.retry(exc=e)  # TODO are we sure we want to do that?

    return True


@shared_task(base=TaskWithFailure, default_retry_delay=5*60, max_retries=288)  # Retry each 5 minutes for 24 hours
def destroy_vm(vm):
    change_vm_power_state(vm, "off")
    try:
        vm_api_request(command='destroy', vmid=vm.name)
    except PlatformsAPIFailure as e:
        return on_vm_api_failure(*e.args)
    except Exception as e:
        raise destroy_vm.retry(exc=e)

    return True


def clone_vm(site, primary_vm):
    delete_vm = None

    if primary_vm:
        original_vm = site.primary_vm
        if site.secondary_vm:
            delete_vm = site.secondary_vm
    else:
        original_vm = site.secondary_vm
        if site.primary_vm:
            delete_vm = site.primary_vm

    if delete_vm:
        delete_vm.site = None
        delete_vm.save()

    destination_vm = VirtualMachine.objects.create(primary=(not primary_vm),
                                                   status='requested', token=uuid.uuid4(), site=site,
                                                   network_configuration=NetworkConfig.get_free_config())
    clone_vm_api_call.delay(original_vm, destination_vm, delete_vm)


@shared_task(base=TaskWithFailure, default_retry_delay=5*60, max_retries=288)  # Retry each 5 minutes for 24 hours
def clone_vm_api_call(original_vm, destination_vm, delete_vm):
    if delete_vm:
        delete_vm.delete()
    try:
        response = vm_api_request(command='clone', vmid=original_vm.name,
                                  ip=destination_vm.ipv4,
                                  hostname=destination_vm.hostname)
    except PlatformsAPIFailure as e:
        return on_vm_api_failure(*e.args)
    except Exception as e:
        raise clone_vm_api_call.retry(exc=e)

    destination_vm.name = response['vmid']
    destination_vm.status = 'ready'
    destination_vm.save()

    # Copy Unix Groups
    for unix_group in original_vm.unix_groups.all():
        copy_users = unix_group.users.all()
        unix_group.pk = None
        unix_group.vm = destination_vm
        unix_group.save()
        unix_group.users = copy_users

    # Copy Ansible Configuration
    for ansible_conf in original_vm.ansible_configuration.all():
        ansible_conf.pk = None
        ansible_conf.vm = destination_vm
        ansible_conf.save()

    # Copy vhosts
    # TODO copy Domain Names
    for vhost in original_vm.vhosts.all():
        vhost.pk = None
        vhost.vm = destination_vm
        vhost.save()

    return True

import logging
import subprocess
from celery import shared_task, Task
from django.conf import settings
from django.utils import timezone

from apimws.utils import execute_userv_process
from sitesmanagement.models import Site, Snapshot, Service, Vhost


LOGGER = logging.getLogger('mws')


class UnexpectedVMStatus(Exception):
    pass


def refresh_object(obj):
    """ Reload an object from the database """
    return obj.__class__._default_manager.get(pk=obj.pk)


def launch_ansible(service):
    if service.status == 'ready':
        service.status = 'ansible'
        service.save()
        launch_ansible_async.delay(service)
    elif service.status == 'ansible':
        service.status = 'ansible_queued'
        service.save()
    elif service.status == 'ansible_queued':
        return
    elif service.status in ['installing', 'postinstall']:
        return
    else:
        raise UnexpectedVMStatus()  # TODO pass the vm object?


def launch_ansible_by_user(user):
    for site in Site.objects.all():
        if user in site.list_of_all_type_of_active_users() and not site.is_canceled():
            launch_ansible_site(site)  # TODO: Change this to other thing more sensible


def launch_ansible_site(site):
    if site.production_service and site.production_service.active:
        launch_ansible(site.production_service)
    if site.test_service and site.test_service.active:
        launch_ansible(site.test_service)


class AnsibleTaskWithFailure(Task):
    """If you want to use this task with failure be sure that the first argument is the Service"""
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if type(exc) is subprocess.CalledProcessError:
            LOGGER.error("An error happened when trying to execute Ansible.\nThe task id is %s.\n\n"
                         "The parameters passed to the task were: \nargs: %s\nkwargs: %s\n\nThe traceback is:\n%s\n\n"
                         "The output from the command was: %s\n", task_id, args, kwargs, einfo, exc.output)
        else:
            LOGGER.error("An error happened when trying to execute Ansible.\nThe task id is %s.\n\n"
                         "The parameters passed to the task were: \nargs: %s\nkwargs: %s\n\nThe traceback is:\n%s\n",
                         task_id, args, kwargs, einfo)
        if args[0].__class__ == Service:
            service = args[0]
            service.status = 'ready'
            service.save()


@shared_task(base=AnsibleTaskWithFailure, default_retry_delay=120, max_retries=2)
def launch_ansible_async(service, ignore_host_key=False):
    while service.status != 'ready':
        try:
            for vm in service.virtual_machines.all():
                userv_cmd = []
                if ignore_host_key:
                    userv_cmd.extend(["--defvar", "ANSIBLE_HOST_KEY_CHECKING=False"])
                userv_cmd.extend(["mws-admin", "mws_ansible_host", vm.network_configuration.name])
                execute_userv_process([
                    'ssh', '-i', settings.USERV_SSH_KEY, settings.USERV_SSH_TARGET, " ".join(userv_cmd)
                ], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            raise launch_ansible_async.retry(exc=e)
        service = refresh_object(service)
        if service.status == 'ansible_queued':
            service.status = 'ansible'
            service.save()
        else:
            service.status = 'ready'
            service.save()
        # Delete Unix Groups marked to be deleted after ansible has finished deleting them from the system
        service.unix_groups.filter(to_be_deleted=True).delete()


@shared_task(base=AnsibleTaskWithFailure)
def ansible_change_mysql_root_pwd(service):
    execute_playbook_on_vms(service, ["--tags", "change_mysql_root_pwd", "-e", "change_mysql_root_pwd=true"])


@shared_task(base=AnsibleTaskWithFailure)
def ansible_create_custom_snapshot(service, snapshot):
    try:
        execute_playbook_on_vms(service, [
            "--tags", "create_custom_snapshot", "-e", 'create_snapshot_name="%s"' % snapshot.name
        ])
        snapshot.date = timezone.now()
        snapshot.save()
    except Exception as e:
        snapshot.delete()
        raise e


@shared_task(base=AnsibleTaskWithFailure)
def restore_snapshot(service, snapshot_name):
    execute_playbook_on_vms(service, ["--tags", "restore_snapshot", "-e", 'restore_snapshot_name="%s"' % snapshot_name])


@shared_task(base=AnsibleTaskWithFailure)
def delete_snapshot(snapshot_id):
    snapshot = Snapshot.objects.get(id=snapshot_id)
    execute_playbook_on_vms(snapshot.service, [
        "--tags", "delete_snapshot", "-e", 'delete_snapshot_name="%s"' % snapshot.name
    ])
    snapshot.delete()


def execute_playbook_on_vms(service, playbook_args):
    """
    Execute the ansible MWS guest role against all VMs for a specified Service instance.

    :param service: the service of the target VMs
    :param playbook_args: ansible playbook arguments
    """
    for vm in service.virtual_machines.all():
        cmd = ["mws-admin", "mws_ansible_host_d", vm.network_configuration.name]
        cmd.extend(playbook_args)
        execute_userv_process(cmd, stderr=subprocess.STDOUT)
    return


@shared_task(base=AnsibleTaskWithFailure)
def delete_vhost_ansible(service, vhost_name, vhost_webapp):
    """delete the vhost folder and all its contents"""
    for vm in service.virtual_machines.all():
        execute_userv_process([
            "mws-admin", "mws_delete_vhost", vm.network_configuration.name, "--tags", "delete_vhost",
            "-e", "delete_vhost_name=%s delete_vhost_webapp=%s" % (vhost_name, vhost_webapp)
        ], stderr=subprocess.STDOUT)
    launch_ansible(service)
    return


@shared_task(base=AnsibleTaskWithFailure)
def vhost_enable_apache_owned(vhost_id):
    """Changes ownership of the docroot folder to the user www-data"""
    vhost = Vhost.objects.get(id=vhost_id)
    for vm in vhost.service.virtual_machines.all():
        execute_userv_process([
            "mws-admin", "mws_vhost_owner", vm.network_configuration.name, vhost.name, "enable"
        ], stderr=subprocess.STDOUT)
    vhost.apache_owned = True
    vhost.save()
    vhost_disable_apache_owned.apply_async(args=(vhost_id,), countdown=3600)  # Leave an hour to the user


@shared_task(base=AnsibleTaskWithFailure)
def vhost_disable_apache_owned(vhost_id):
    """Revert the ownership of the docroot folder back to site-admin"""
    vhost = Vhost.objects.get(id=vhost_id)
    for vm in vhost.service.virtual_machines.all():
        execute_userv_process([
            "mws-admin", "mws_vhost_owner", vm.network_configuration.name, vhost.name, "disable"
        ], stderr=subprocess.STDOUT)
    vhost.apache_owned = False
    vhost.save()

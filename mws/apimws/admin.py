from django.contrib import admin
from django.contrib.admin import ModelAdmin
from apimws.models import AnsibleConfiguration


class AnsibleConfigurationAdmin(ModelAdmin):

    model = AnsibleConfiguration
    list_display = ('key', 'value', 'site')


admin.site.register(AnsibleConfiguration, AnsibleConfigurationAdmin)
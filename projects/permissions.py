import rules
from rest_framework import permissions

class CanAlterDeleteProject(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):

        if request.method == "GET":
            return request.user.has_perm('projects.can_view_project', obj)
        else:
            return request.user.has_perm('projects.can_alter_or_delete_project', obj)
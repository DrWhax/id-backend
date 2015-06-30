var ID2 = ID2 || {};
ID2.Projects = angular.module('ID2Projects', ['ngMaterial']);
ID2.Projects.config(function($interpolateProvider) {
  $interpolateProvider.startSymbol('[[');
  $interpolateProvider.endSymbol(']]');
});

ID2.Projects.controller('ID2ProjectsController', ['$scope', '$mdSidenav', '$mdDialog', '$http',  function($scope, $mdSidenav, $mdDialog, $http) {
    $scope.toggleSidenav = function(menuId) {
        $mdSidenav(menuId).toggle();
    };

    $scope.goto = function(item) {
        console.log("going to " + item);
    }

    $scope.newProject = function(ev) {
        $mdDialog.show({
            controller: DialogController,
            templateUrl: '/static/html/id2/project.new.html',
            parent: angular.element(document.body),
            targetEvent: ev,
        })
        .then(function(data) {
            console.log(data);
            $http.post('/api/projects/', data).
                success(function(data, status, headers, config) {
                    console.log("Success:" + data);
                    $scope.projectListUpdate();
                }).
                error(function(data, status, headers, config) {
                    console.log("Error:" + data);
                });
            $scope.alert = data;
        }, function() {
            $scope.alert = 'You cancelled the dialog.';
        });
    };

    $scope.projectListUpdate = function() {
        $http.get('/api/projects/').
            success(function(data, status, headers, config) {
                $scope.projectList = data;
            }).
            error(function(data, status, headers, config) {
                // log error
            });
    }

    $http.defaults.xsrfHeaderName = 'X-CSRFToken';
    $http.defaults.xsrfCookieName = 'csrftoken';
    $scope.projectList = []
    $scope.projectListUpdate();

    this.menuitems = [
        {"icon": "fa-search", "name": "Search"},
        {"icon": "fa-database", "name": "Databases"},
        {"icon": "fa-ticket", "name": "Tickets"},
        {"icon": "fa-folder", "name": "Projects"},
    ];
    this.appselected = this.menuitems[1];

    function DialogController($scope, $mdDialog) {
        $scope.hide = function() {
            $mdDialog.hide();
        };
        $scope.cancel = function() {
            $mdDialog.cancel();
        };
        $scope.create = function(data) {
            $mdDialog.hide(data);
        };
    }

}]);
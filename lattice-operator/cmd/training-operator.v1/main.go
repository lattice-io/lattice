/*
Copyright 2021.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package main

import (
	"flag"
	"fmt"
	"os"
	"strconv"

	"go.uber.org/zap/zapcore"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	_ "k8s.io/client-go/plugin/pkg/client/auth"
	"k8s.io/client-go/rest"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/config"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"

	breezemlv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	"github.com/breezeml/lattice-operator/pkg/billing"
	"github.com/breezeml/lattice-operator/pkg/billing/license"
	"github.com/breezeml/lattice-operator/pkg/billing/usage"
	controllerv1 "github.com/breezeml/lattice-operator/pkg/controller"
	"github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/common/util"
	latticeconfig "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/config"
	"github.com/sirupsen/logrus"
	//+kubebuilder:scaffold:imports
)

const (
	kubeContextEnv = "KUBE_CONTEXT"
)

var (
	scheme   = runtime.NewScheme()
	setupLog = ctrl.Log.WithName("setup")

	// The following variables are set by the build system
	// Secrets related to lemon squeezy license checking
	lemonSqueezyStoreID     string
	lemonSqueezyProductID   string
	lemonSqueezyProductName string
	// Secrets related to the grafana cloud monitoring service
	grafanaCloudURL      string
	grafanaCloudUserName string
	grafanaCloudPassword string

	// The billing daemon handles license validation and metric pushing periodically
	billingDaemon *billing.Daemon
)

func init() {
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
	utilruntime.Must(breezemlv1.AddToScheme(scheme))
	//+kubebuilder:scaffold:scheme

	// Set up secret variables for the billing daemon
	usage.GrafanaCloudURL = grafanaCloudURL
	usage.GrafanaCloudUserName = grafanaCloudUserName
	usage.GrafanaCloudPassword = grafanaCloudPassword
	license.LemonSqueezyStoreID, _ = strconv.Atoi(lemonSqueezyStoreID)
	license.LemonSqueezyProductID, _ = strconv.Atoi(lemonSqueezyProductID)
	license.LemonSqueezyProductName = lemonSqueezyProductName
}

// Initialize the lattice configurations
func initConfig(namespace string) *latticeconfig.LatticeConfig {
	jobNodeSelector := util.GetJobNodeSelector()
	jfrogSecret, _ := util.GetJfrogSecret()
	resourceUnit := util.GetResourceType()
	debugWorldSize, _ := util.GetDebugWorldSize()

	return &latticeconfig.LatticeConfig{
		Namespace:                       namespace,
		JobNodeSelector:                 jobNodeSelector,
		JFrogSecret:                     jfrogSecret,
		ResourceUnit:                    resourceUnit,
		DebugWorldSize:                  debugWorldSize,
		LatticeAddonsCheckpointType:     util.GetLatticeAddonsCheckpointType(),
		LatticeAddonsCheckpointEndpoint: util.GetLatticeAddonsCheckpointEndpoint(),
		LatticeAddonsCheckpointPort:     util.GetLatticeAddonsCheckpointPort(),
		LatticeAgentRendezvousBackend:   util.GetLatticeAgentRendezvousBackend(),
		LatticeAgentRendezvousEndpoint:  util.GetLatticeAgentRendezvousEndpoint(),
		LatticeAgentRendezvousPort:      util.GetLatticeAgentRendezvousPort(),
	}
}

func setLogLevel() {
	lvl, ok := os.LookupEnv("LOG_LEVEL")
	if !ok {
		lvl = "warning"
	}

	level, err := logrus.ParseLevel(lvl)
	if err != nil {
		level = logrus.WarnLevel
	}

	logrus.SetLevel(level)
}

func main() {
	/*
		to maintain a minimal working lattice controller, we remove the following things from the original main.go function
		1. removing framework specific job apis and controllers (e.g., pytorchjob, tensorflowjob)
		2. designing the minimal working trainingjob api
		3. implementing a (non-elastic for now) controller for trainingjobs
		TODO: be more specific in later PRs
	*/
	var metricsAddr string
	var enableLeaderElection bool
	var probeAddr string
	var EnabledControllers controllerv1.EnabledControllers
	var namespace string
	var monitoringPort int

	flag.StringVar(&metricsAddr, "metrics-bind-address", ":8080", "The address the metric endpoint binds to.")
	flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "The address the probe endpoint binds to.")
	flag.BoolVar(&enableLeaderElection, "leader-elect", false,
		"Enable leader election for controller manager, will ensure there is only one active controller manager.")
	flag.StringVar(&namespace, "namespace", "",
		"The namespace to monitor lattice jobs. If unset, it monitors all namespaces cluster-wide.")
	flag.IntVar(&monitoringPort, "monitoring-port", 9443, "Endpoint port for displaying monitoring metrics. ")

	setLogLevel()

	opts := zap.Options{
		Development:     true,
		StacktraceLevel: zapcore.DPanicLevel,
	}
	opts.BindFlags(flag.CommandLine)
	flag.Parse()

	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))

	// If we set up KUBE_CONTEXT, try to launch the operator with the context
	// Otherwise we use $HOME/.kube/config
	var cfg *rest.Config
	if kubeContext, ok := os.LookupEnv(kubeContextEnv); ok {
		var err error
		cfg, err = config.GetConfigWithContext(kubeContext)
		if err != nil {
			setupLog.Error(err, "unable to get kubeconfig")
			os.Exit(1)
		}
	} else {
		cfg = ctrl.GetConfigOrDie()
	}

	// Get the billing daemon
	billingDaemon = billing.NewDaemon()
	billingDaemon.Start()

	// Get the lattice config
	latticeConfig := initConfig(namespace)

	mgr, err := ctrl.NewManager(cfg, ctrl.Options{
		Scheme:                 scheme,
		MetricsBindAddress:     metricsAddr,
		Port:                   monitoringPort,
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "1ca428e5.",
		Namespace:              namespace,
	})
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}

	EnabledControllers.FillAll()
	for _, c := range EnabledControllers {
		setupFunc, supported := controllerv1.SupportedControllers[c]
		if !supported {
			setupLog.Error(fmt.Errorf("cannot find %s in supportedController", c),
				"controller not supported", "controller", c)
			os.Exit(1)
		}
		if err = setupFunc(mgr, billingDaemon, latticeConfig); err != nil {
			setupLog.Error(err, "unable to create controller", "controller", c)
			os.Exit(1)
		}
	}
	//+kubebuilder:scaffold:builder

	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up ready check")
		os.Exit(1)
	}

	setupLog.Info("starting manager")
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}

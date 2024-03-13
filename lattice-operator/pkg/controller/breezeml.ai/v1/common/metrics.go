// // Derived from kubeflow/training-operator

package common

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"sigs.k8s.io/controller-runtime/pkg/metrics"

	dto "github.com/prometheus/client_model/go"
	"github.com/sirupsen/logrus"
)

// Define all the prometheus counters for all jobs
var (
	jobsCreatedCount = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "training_operator_jobs_created_total",
			Help: "Counts number of jobs created",
		},
		[]string{"job_namespace", "framework"},
	)
	jobsDeletedCount = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "training_operator_jobs_deleted_total",
			Help: "Counts number of jobs deleted",
		},
		[]string{"job_namespace", "framework"},
	)
	jobsSuccessfulCount = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "training_operator_jobs_successful_total",
			Help: "Counts number of jobs successful",
		},
		[]string{"job_namespace", "framework"},
	)
	jobsFailedCount = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "training_operator_jobs_failed_total",
			Help: "Counts number of jobs failed",
		},
		[]string{"job_namespace", "framework"},
	)
	jobsRestartedCount = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "training_operator_jobs_restarted_total",
			Help: "Counts number of jobs restarted",
		},
		[]string{"job_namespace", "framework"},
	)

	livePodsGauge = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "training_operator_live_pods_total",
			Help: "Gauge of number of live pods",
		},
		[]string{"job_namespace", "job_id"},
	)

	runningPodsGauge = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "training_operator_running_pods_total",
			Help: "Gauge of number of running pods",
		},
		[]string{"job_namespace", "job_id"},
	)

	clusterSizeGauge = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "training_operator_cluster_size",
			Help: "Gauge of the cluster size (number of resource units)",
		},
	)

	activeSizeGauge = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "training_operator_active_size",
			Help: "Gauge of the active size (number of resource units), e.g., number of GPUs in use",
		},
	)
)

func init() {
	// Register custom metrics with the global prometheus registry
	metrics.Registry.MustRegister(jobsCreatedCount,
		jobsDeletedCount,
		jobsSuccessfulCount,
		jobsFailedCount,
		jobsRestartedCount,
		livePodsGauge,
		runningPodsGauge,
		clusterSizeGauge,
		activeSizeGauge,
	)
}

func GetCounterValue(job_namespace, job_id string, metric *prometheus.GaugeVec) float64 {
	var m = &dto.Metric{}
	if err := metric.WithLabelValues(job_namespace, job_id).Write(m); err != nil {
		logrus.Error(err, "Could not get the counter of", "job_namespace", job_namespace, "job_id", job_id)
		return 0
	}
	return m.Counter.GetValue()
}

func LivePodsGaugeInc(job_namespace, job_id string) {
	livePodsGauge.WithLabelValues(job_namespace, job_id).Inc()
}

func LivePodsGaugeDec(job_namespace, job_id string) {
	livePodsGauge.WithLabelValues(job_namespace, job_id).Dec()
}

func LivePodsGaugeGetValue(job_namespace, job_id string) float64 {
	return GetCounterValue(job_namespace, job_id, livePodsGauge)
}

func LivePodsGaugeDeleteMetric(job_namespace, job_id string) {
	livePodsGauge.DeleteLabelValues(job_namespace, job_id)
}

func LivePodsGaugeSetValue(job_namespace, job_id string, curr_size int32) {
	livePodsGauge.WithLabelValues(job_namespace, job_id).Set(float64(curr_size))
}

func LivePodsGaugeDeleteAllMetrics() {
	livePodsGauge.Reset()
}

func RunningPodsGaugeSetValue(job_namespace, job_id string, curr_size int32) {
	runningPodsGauge.WithLabelValues(job_namespace, job_id).Set(float64(curr_size))
}

func RunningPodsGaugeDeleteMetric(job_namespace, job_id string) {
	runningPodsGauge.DeleteLabelValues(job_namespace, job_id)
}

func ClusterSizeGaugeSetValue(cluster_size int32) {
	clusterSizeGauge.Set(float64(cluster_size))
}

func ActiveSizeGaugeSetValue(active_size int32) {
	activeSizeGauge.Set(float64(active_size))
}

func ActiveSizeGaugeGetValue() float64 {
	var m = &dto.Metric{}
	if err := activeSizeGauge.Write(m); err != nil {
		logrus.Error(err, "Could not get the counter of", "active_size")
		return 0
	}
	return m.Gauge.GetValue()
}

func CreatedJobsCounterInc(job_namespace, framework string) {
	jobsCreatedCount.WithLabelValues(job_namespace, framework).Inc()
}

func DeletedJobsCounterInc(job_namespace, framework string) {
	jobsDeletedCount.WithLabelValues(job_namespace, framework).Inc()
}

func SuccessfulJobsCounterInc(job_namespace, framework string) {
	jobsSuccessfulCount.WithLabelValues(job_namespace, framework).Inc()
}

func FailedJobsCounterInc(job_namespace, framework string) {
	jobsFailedCount.WithLabelValues(job_namespace, framework).Inc()
}

func RestartedJobsCounterInc(job_namespace, framework string) {
	jobsRestartedCount.WithLabelValues(job_namespace, framework).Inc()
}

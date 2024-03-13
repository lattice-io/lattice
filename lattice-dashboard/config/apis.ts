export function getBackendURL() {
  // change to /api for deployment.
  // change to http://localhost:8080/api for local testing.
  return `/api`
}

// TODO(p0): Make the grafana sub-path configurable and make sure it is consistent with the grafana helm chart and ingress
// TODO(p1): Find a better grafana dashboard identifier, not "5yjpWJ0Vk", or make it configurable
// TODO(p2): Try to avoid inline query parameters
export function getMonitorURL() {
  // TODO: Support a URL for local development
  return '/grafana/d/5yjpWJ0Vk/kubernetes-compute-resources-lattice-pod?var-datasource=prometheus&var-lattice_job_name='
}

export const colors = [
  '#008FFB', '#00E396', '#FEB019', '#FF4560', '#775DD0',
  '#3F51B5', '#03A9F4', '#4CAF50', '#F9CE1D', '#FF9800',
  '#33B2DF', '#546E7A', 'D4526E', '13D8AA', 'A5978B',
  '4ECDC4', 'C7F464', '81D4FA', '546E7A', 'FD6A6A',
  '2B908F', 'F9A3A4', '90EE7E', 'FA4443', '69D2E7',
  '449DD1', 'F86624', 'EA3546', '662E9B', 'C5D86D']

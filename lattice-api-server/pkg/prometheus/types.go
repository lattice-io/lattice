package prometheus

import (
	"encoding/json"
	"strconv"
)

type PrometheusMatrixResponse struct {
	Status string               `json:"status"`
	Data   PrometheusMatrixData `json:"data"`
}

type PrometheusMatrixData struct {
	ResultType string                  `json:"resultType"`
	Result     []PrometheusMatrixEntry `json:"result"`
}

type PrometheusMatrixEntry struct {
	Metric map[string]string `json:"metric"`
	Values []PrometheusValue `json:"values"`
}

type PrometheusValue struct {
	Time  float64 `json:"time"`
	Value float64 `json:"value"`
}

func (v *PrometheusValue) UnmarshalJSON(p []byte) error {
	var tmp []interface{}
	if err := json.Unmarshal(p, &tmp); err != nil {
		return err
	}
	v.Time = tmp[0].(float64)
	value, err := strconv.ParseFloat(tmp[1].(string), 64)
	if err != nil {
		return err
	}
	v.Value = value
	return nil
}

type TimeSeries map[string][]PrometheusValue

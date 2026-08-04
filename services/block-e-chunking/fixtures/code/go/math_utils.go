package main

import (
	"fmt"
	"math"
	"sort"
)

type MathUtils struct{}

func NewMathUtils() *MathUtils {
	return &MathUtils{}
}

func (m *MathUtils) Mean(values []float64) float64 {
	if len(values) == 0 {
		return 0.0
	}
	sum := 0.0
	for _, v := range values {
		sum += v
	}
	return sum / float64(len(values))
}

func (m *MathUtils) Median(values []float64) float64 {
	if len(values) == 0 {
		return 0.0
	}
	sorted := make([]float64, len(values))
	copy(sorted, values)
	sort.Float64s(sorted)
	n := len(sorted)
	if n%2 == 0 {
		return (sorted[n/2-1] + sorted[n/2]) / 2.0
	}
	return sorted[n/2]
}

func (m *MathUtils) StdDev(values []float64) float64 {
	if len(values) == 0 {
		return 0.0
	}
	mean := m.Mean(values)
	sum := 0.0
	for _, v := range values {
		diff := v - mean
		sum += diff * diff
	}
	variance := sum / float64(len(values))
	return math.Sqrt(variance)
}

func (m *MathUtils) Percentile(values []float64, p float64) float64 {
	if len(values) == 0 {
		return 0.0
	}
	sorted := make([]float64, len(values))
	copy(sorted, values)
	sort.Float64s(sorted)
	n := len(sorted)
	k := float64(n-1) * p / 100.0
	f := math.Floor(k)
	c := math.Ceil(k)
	if f == c {
		return sorted[int(k)]
	}
	d0 := sorted[int(f)] * (c - k)
	d1 := sorted[int(c)] * (k - f)
	return d0 + d1
}

func main() {
	utils := NewMathUtils()
	values := []float64{1.0, 2.0, 3.0, 4.0, 5.0}
	fmt.Printf("Mean: %.2f\n", utils.Mean(values))
	fmt.Printf("Median: %.2f\n", utils.Median(values))
	fmt.Printf("StdDev: %.2f\n", utils.StdDev(values))
	fmt.Printf("Percentile 50: %.2f\n", utils.Percentile(values, 50))
}

#!/usr/bin/env python3
# ======================================
# GRID CLASH - METRICS ANALYSIS & VISUALIZATION
# ======================================
#
# PURPOSE: Analyze collected metrics and generate plots
# Produces:
#   - Summary statistics (mean, median, 95th percentile)
#   - Comparison across test scenarios
#   - Visualizations (latency, jitter, position error, bandwidth)
#
# USAGE:
#   python analyze_metrics.py --results-dir results --plots-dir plots
#
# ======================================

import os
import sys
import csv
import argparse
import statistics
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Try to import plotting libraries
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[WARN] matplotlib not installed. Plots will not be generated.")
    print("       Install with: pip install matplotlib")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def load_csv(filepath):
    """Load metrics from a CSV file."""
    metrics = []
    try:
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                for key in ['client_id', 'msg_type', 'snapshot_id', 'seq_num',
                           'server_timestamp_ms', 'recv_time_ms', 'latency_ms',
                           'jitter_ms', 'perceived_position_error', 'cpu_percent',
                           'bandwidth_per_client_kbps']:
                    if key in row and row[key]:
                        try:
                            row[key] = float(row[key])
                        except ValueError:
                            pass
                metrics.append(row)
    except Exception as e:
        print(f"[ERROR] Failed to load {filepath}: {e}")
    return metrics


def calculate_statistics(values):
    """Calculate mean, median, and 95th percentile."""
    if not values:
        return {'mean': 0, 'median': 0, 'p95': 0, 'min': 0, 'max': 0, 'count': 0}
    
    sorted_vals = sorted(values)
    p95_idx = int(len(sorted_vals) * 0.95)
    
    return {
        'mean': statistics.mean(values),
        'median': statistics.median(values),
        'p95': sorted_vals[min(p95_idx, len(sorted_vals)-1)],
        'min': min(values),
        'max': max(values),
        'count': len(values)
    }


def analyze_scenario(metrics):
    """Analyze metrics for a single scenario."""
    if not metrics:
        return {}
    
    # Extract values for analysis
    latencies = [m['latency_ms'] for m in metrics 
                 if isinstance(m.get('latency_ms'), (int, float)) and m['latency_ms'] > 0]
    jitters = [m['jitter_ms'] for m in metrics 
               if isinstance(m.get('jitter_ms'), (int, float)) and m['jitter_ms'] >= 0]
    errors = [m['perceived_position_error'] for m in metrics 
              if isinstance(m.get('perceived_position_error'), (int, float))]
    cpu = [m['cpu_percent'] for m in metrics 
           if isinstance(m.get('cpu_percent'), (int, float))]
    bandwidth = [m['bandwidth_per_client_kbps'] for m in metrics 
                 if isinstance(m.get('bandwidth_per_client_kbps'), (int, float))]
    
    # Count message types
    msg_types = defaultdict(int)
    for m in metrics:
        msg_types[m.get('msg_type_name', 'UNKNOWN')] += 1
    
    return {
        'latency': calculate_statistics(latencies),
        'jitter': calculate_statistics(jitters),
        'position_error': calculate_statistics(errors),
        'cpu': calculate_statistics(cpu),
        'bandwidth': calculate_statistics(bandwidth),
        'total_packets': len(metrics),
        'message_types': dict(msg_types),
        'unique_clients': len(set(m.get('client_id', 0) for m in metrics))
    }


def check_acceptance_criteria(scenario_name, analysis):
    """Check if scenario meets acceptance criteria from Section 4.1."""
    results = []
    
    if 'baseline' in scenario_name.lower():
        # Baseline: avg latency ≤ 50 ms; avg CPU < 60%
        latency_ok = analysis['latency']['mean'] <= 50
        cpu_ok = analysis['cpu']['mean'] < 60
        results.append(('Avg Latency ≤ 50ms', latency_ok, 
                       f"{analysis['latency']['mean']:.2f}ms"))
        results.append(('Avg CPU < 60%', cpu_ok, 
                       f"{analysis['cpu']['mean']:.2f}%"))
        
    elif 'loss_2' in scenario_name.lower() or '2%' in scenario_name:
        # Loss 2%: Mean position error ≤ 0.5 units; 95th ≤ 1.5 units
        error_mean_ok = analysis['position_error']['mean'] <= 0.5
        error_p95_ok = analysis['position_error']['p95'] <= 1.5
        results.append(('Mean Position Error ≤ 0.5', error_mean_ok,
                       f"{analysis['position_error']['mean']:.4f}"))
        results.append(('P95 Position Error ≤ 1.5', error_p95_ok,
                       f"{analysis['position_error']['p95']:.4f}"))
        
    elif 'loss_5' in scenario_name.lower() or '5%' in scenario_name:
        # Loss 5%: System remains stable (no crashes, reasonable latency)
        stable = analysis['total_packets'] > 0 and analysis['latency']['mean'] < 500
        results.append(('System Stable', stable,
                       f"{analysis['total_packets']} packets"))
        
    elif 'delay' in scenario_name.lower():
        # Delay 100ms: Clients continue functioning
        functioning = analysis['total_packets'] > 0
        results.append(('Clients Functioning', functioning,
                       f"{analysis['total_packets']} packets"))
    
    return results


def generate_report(scenarios, output_file):
    """Generate a text report of the analysis."""
    lines = []
    lines.append("=" * 70)
    lines.append("GRID CLASH - METRICS ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    for name, analysis in scenarios.items():
        lines.append("-" * 70)
        lines.append(f"SCENARIO: {name}")
        lines.append("-" * 70)
        lines.append("")
        
        lines.append(f"Total Packets: {analysis['total_packets']}")
        lines.append(f"Unique Clients: {analysis['unique_clients']}")
        lines.append("")
        
        lines.append("Message Types:")
        for msg_type, count in analysis['message_types'].items():
            lines.append(f"  {msg_type}: {count}")
        lines.append("")
        
        lines.append("LATENCY (ms):")
        lines.append(f"  Mean:   {analysis['latency']['mean']:.2f}")
        lines.append(f"  Median: {analysis['latency']['median']:.2f}")
        lines.append(f"  P95:    {analysis['latency']['p95']:.2f}")
        lines.append(f"  Min:    {analysis['latency']['min']:.2f}")
        lines.append(f"  Max:    {analysis['latency']['max']:.2f}")
        lines.append("")
        
        lines.append("JITTER (ms):")
        lines.append(f"  Mean:   {analysis['jitter']['mean']:.2f}")
        lines.append(f"  Median: {analysis['jitter']['median']:.2f}")
        lines.append(f"  P95:    {analysis['jitter']['p95']:.2f}")
        lines.append("")
        
        lines.append("POSITION ERROR (units):")
        lines.append(f"  Mean:   {analysis['position_error']['mean']:.4f}")
        lines.append(f"  Median: {analysis['position_error']['median']:.4f}")
        lines.append(f"  P95:    {analysis['position_error']['p95']:.4f}")
        lines.append("")
        
        lines.append("CPU USAGE (%):")
        lines.append(f"  Mean:   {analysis['cpu']['mean']:.2f}")
        lines.append(f"  Max:    {analysis['cpu']['max']:.2f}")
        lines.append("")
        
        lines.append("BANDWIDTH (kbps per client):")
        lines.append(f"  Mean:   {analysis['bandwidth']['mean']:.2f}")
        lines.append("")
        
        # Acceptance criteria check
        criteria = check_acceptance_criteria(name, analysis)
        if criteria:
            lines.append("ACCEPTANCE CRITERIA:")
            for criterion, passed, value in criteria:
                status = "✓ PASS" if passed else "✗ FAIL"
                lines.append(f"  [{status}] {criterion}: {value}")
            lines.append("")
    
    lines.append("=" * 70)
    
    report_text = "\n".join(lines)
    
    # Save to file
    with open(output_file, 'w') as f:
        f.write(report_text)
    
    print(report_text)
    return report_text


def generate_comparison_csv(scenarios, output_file):
    """Generate a CSV comparing all scenarios."""
    rows = []
    
    for name, analysis in scenarios.items():
        row = {
            'scenario': name,
            'total_packets': analysis['total_packets'],
            'unique_clients': analysis['unique_clients'],
            'latency_mean': analysis['latency']['mean'],
            'latency_median': analysis['latency']['median'],
            'latency_p95': analysis['latency']['p95'],
            'jitter_mean': analysis['jitter']['mean'],
            'jitter_median': analysis['jitter']['median'],
            'jitter_p95': analysis['jitter']['p95'],
            'position_error_mean': analysis['position_error']['mean'],
            'position_error_median': analysis['position_error']['median'],
            'position_error_p95': analysis['position_error']['p95'],
            'cpu_mean': analysis['cpu']['mean'],
            'cpu_max': analysis['cpu']['max'],
            'bandwidth_mean': analysis['bandwidth']['mean']
        }
        rows.append(row)
    
    if rows:
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"[INFO] Comparison CSV saved to {output_file}")


def generate_plots(scenarios, raw_metrics, plots_dir):
    """Generate visualization plots."""
    if not HAS_MATPLOTLIB:
        print("[WARN] Skipping plot generation (matplotlib not installed)")
        return
    
    os.makedirs(plots_dir, exist_ok=True)
    
    scenario_names = list(scenarios.keys())
    
    # 1. Latency Comparison Bar Chart
    fig, ax = plt.subplots(figsize=(10, 6))
    x = range(len(scenario_names))
    means = [scenarios[s]['latency']['mean'] for s in scenario_names]
    medians = [scenarios[s]['latency']['median'] for s in scenario_names]
    p95s = [scenarios[s]['latency']['p95'] for s in scenario_names]
    
    width = 0.25
    ax.bar([i - width for i in x], means, width, label='Mean', color='steelblue')
    ax.bar(x, medians, width, label='Median', color='lightsteelblue')
    ax.bar([i + width for i in x], p95s, width, label='P95', color='darkblue')
    
    ax.set_xlabel('Scenario')
    ax.set_ylabel('Latency (ms)')
    ax.set_title('Latency Comparison Across Scenarios')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenario_names], fontsize=8)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'latency_comparison.png'), dpi=150)
    plt.close()
    
    # 2. Jitter Comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    means = [scenarios[s]['jitter']['mean'] for s in scenario_names]
    p95s = [scenarios[s]['jitter']['p95'] for s in scenario_names]
    
    width = 0.35
    ax.bar([i - width/2 for i in x], means, width, label='Mean', color='coral')
    ax.bar([i + width/2 for i in x], p95s, width, label='P95', color='darkorange')
    
    ax.set_xlabel('Scenario')
    ax.set_ylabel('Jitter (ms)')
    ax.set_title('Jitter Comparison Across Scenarios')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenario_names], fontsize=8)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'jitter_comparison.png'), dpi=150)
    plt.close()
    
    # 3. Position Error Comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    means = [scenarios[s]['position_error']['mean'] for s in scenario_names]
    p95s = [scenarios[s]['position_error']['p95'] for s in scenario_names]
    
    width = 0.35
    ax.bar([i - width/2 for i in x], means, width, label='Mean', color='seagreen')
    ax.bar([i + width/2 for i in x], p95s, width, label='P95', color='darkgreen')
    
    ax.set_xlabel('Scenario')
    ax.set_ylabel('Position Error (units)')
    ax.set_title('Perceived Position Error Across Scenarios')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenario_names], fontsize=8)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Add acceptance criteria line for loss scenarios
    ax.axhline(y=0.5, color='red', linestyle='--', alpha=0.5, label='Mean Threshold (0.5)')
    ax.axhline(y=1.5, color='darkred', linestyle='--', alpha=0.5, label='P95 Threshold (1.5)')
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'position_error_comparison.png'), dpi=150)
    plt.close()
    
    # 4. CPU Usage Comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    means = [scenarios[s]['cpu']['mean'] for s in scenario_names]
    maxes = [scenarios[s]['cpu']['max'] for s in scenario_names]
    
    width = 0.35
    ax.bar([i - width/2 for i in x], means, width, label='Mean', color='mediumpurple')
    ax.bar([i + width/2 for i in x], maxes, width, label='Max', color='darkviolet')
    
    ax.set_xlabel('Scenario')
    ax.set_ylabel('CPU Usage (%)')
    ax.set_title('CPU Usage Across Scenarios')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenario_names], fontsize=8)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(y=60, color='red', linestyle='--', alpha=0.5, label='Threshold (60%)')
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'cpu_comparison.png'), dpi=150)
    plt.close()
    
    # 5. Bandwidth Comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    means = [scenarios[s]['bandwidth']['mean'] for s in scenario_names]
    
    ax.bar(x, means, color='goldenrod')
    ax.set_xlabel('Scenario')
    ax.set_ylabel('Bandwidth (kbps per client)')
    ax.set_title('Average Bandwidth Per Client')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenario_names], fontsize=8)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'bandwidth_comparison.png'), dpi=150)
    plt.close()
    
    # 6. Time series plots for each scenario (latency over time)
    for name, metrics in raw_metrics.items():
        if not metrics:
            continue
        
        # Sort by recv_time
        sorted_metrics = sorted(metrics, key=lambda m: m.get('recv_time_ms', 0))
        
        times = []
        latencies = []
        start_time = sorted_metrics[0].get('recv_time_ms', 0) if sorted_metrics else 0
        
        for m in sorted_metrics:
            if isinstance(m.get('latency_ms'), (int, float)) and m['latency_ms'] > 0:
                times.append((m['recv_time_ms'] - start_time) / 1000.0)  # Convert to seconds
                latencies.append(m['latency_ms'])
        
        if times and latencies:
            fig, ax = plt.subplots(figsize=(12, 4))
            ax.plot(times, latencies, 'b-', alpha=0.7, linewidth=0.5)
            ax.set_xlabel('Time (seconds)')
            ax.set_ylabel('Latency (ms)')
            ax.set_title(f'Latency Over Time - {name}')
            ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            safe_name = name.replace(' ', '_').replace('(', '').replace(')', '').replace('%', 'pct')
            plt.savefig(os.path.join(plots_dir, f'latency_timeline_{safe_name}.png'), dpi=150)
            plt.close()
    
    print(f"[INFO] Plots saved to {plots_dir}")


def find_result_files(results_dir, timestamp=None):
    """Find all result files, optionally filtered by timestamp."""
    result_files = {}
    
    for f in Path(results_dir).glob('*_merged.csv'):
        name = f.stem.replace('_merged', '')
        
        # If timestamp specified, filter
        if timestamp and not name.startswith(timestamp):
            continue
        
        # Extract scenario name
        parts = name.split('_')
        if len(parts) >= 2:
            # Remove timestamp prefix
            if parts[0].isdigit():
                scenario = '_'.join(parts[1:])
            else:
                scenario = name
        else:
            scenario = name
        
        result_files[scenario] = str(f)
    
    # Also check for individual client files if no merged files
    if not result_files:
        for f in Path(results_dir).glob('*.csv'):
            if 'merged' not in f.stem and 'comparison' not in f.stem:
                name = f.stem
                result_files[name] = str(f)
    
    return result_files


def main():
    parser = argparse.ArgumentParser(description='Grid Clash Metrics Analyzer')
    parser.add_argument('--results-dir', type=str, default='results',
                        help='Directory containing result CSV files')
    parser.add_argument('--plots-dir', type=str, default='plots',
                        help='Directory to save plots')
    parser.add_argument('--timestamp', type=str, default=None,
                        help='Filter results by timestamp prefix')
    parser.add_argument('--output-report', type=str, default=None,
                        help='Output report filename')
    
    args = parser.parse_args()
    
    # Find result files
    result_files = find_result_files(args.results_dir, args.timestamp)
    
    if not result_files:
        print(f"[ERROR] No result files found in {args.results_dir}")
        return 1
    
    print(f"[INFO] Found {len(result_files)} result file(s)")
    
    # Load and analyze each file
    scenarios = {}
    raw_metrics = {}
    
    for name, filepath in result_files.items():
        print(f"[INFO] Analyzing: {name}")
        metrics = load_csv(filepath)
        if metrics:
            raw_metrics[name] = metrics
            scenarios[name] = analyze_scenario(metrics)
    
    if not scenarios:
        print("[ERROR] No metrics to analyze")
        return 1
    
    # Generate outputs
    os.makedirs(args.results_dir, exist_ok=True)
    
    # Report
    report_file = args.output_report or os.path.join(args.results_dir, 'analysis_report.txt')
    generate_report(scenarios, report_file)
    
    # Comparison CSV
    comparison_file = os.path.join(args.results_dir, 'scenario_comparison.csv')
    generate_comparison_csv(scenarios, comparison_file)
    
    # Plots
    generate_plots(scenarios, raw_metrics, args.plots_dir)
    
    print(f"\n[SUCCESS] Analysis complete!")
    print(f"  Report: {report_file}")
    print(f"  Comparison: {comparison_file}")
    print(f"  Plots: {args.plots_dir}/")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

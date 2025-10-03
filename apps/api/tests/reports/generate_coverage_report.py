#!/usr/bin/env python3
"""
Generate comprehensive coverage reports
"""
import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd: str, cwd: str = None) -> subprocess.CompletedProcess:
    """Run a command and return the result"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error running command: {cmd}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        sys.exit(1)
    
    return result


def generate_coverage_reports():
    """Generate all coverage reports"""
    api_dir = Path(__file__).parent.parent.parent
    
    print("Generating coverage reports...")
    
    # Generate HTML coverage report
    print("\n1. Generating HTML coverage report...")
    run_command(
        "python -m pytest --cov=app --cov-report=html:htmlcov --cov-report=term-missing tests/",
        cwd=str(api_dir)
    )
    
    # Generate XML coverage report for CI
    print("\n2. Generating XML coverage report...")
    run_command(
        "python -m pytest --cov=app --cov-report=xml:coverage.xml tests/",
        cwd=str(api_dir)
    )
    
    # Generate JSON coverage report
    print("\n3. Generating JSON coverage report...")
    run_command(
        "python -m pytest --cov=app --cov-report=json:coverage.json tests/",
        cwd=str(api_dir)
    )
    
    # Generate coverage report by module
    print("\n4. Generating module-specific coverage reports...")
    modules = [
        "app.models",
        "app.services", 
        "app.repositories",
        "app.api",
        "app.core"
    ]
    
    for module in modules:
        print(f"  - {module}")
        run_command(
            f"python -m pytest --cov={module} --cov-report=html:htmlcov_{module.replace('.', '_')} tests/",
            cwd=str(api_dir)
        )
    
    print("\n✅ Coverage reports generated successfully!")
    print(f"📁 HTML report: {api_dir}/htmlcov/index.html")
    print(f"📁 XML report: {api_dir}/coverage.xml")
    print(f"📁 JSON report: {api_dir}/coverage.json")


def generate_test_execution_report():
    """Generate test execution report"""
    api_dir = Path(__file__).parent.parent.parent
    
    print("\nGenerating test execution report...")
    
    # Generate JUnit XML report
    run_command(
        "python -m pytest --junitxml=test-results/results.xml tests/",
        cwd=str(api_dir)
    )
    
    # Generate detailed test report
    run_command(
        "python -m pytest --html=test-results/report.html --self-contained-html tests/",
        cwd=str(api_dir)
    )
    
    print("✅ Test execution reports generated!")
    print(f"📁 JUnit XML: {api_dir}/test-results/results.xml")
    print(f"📁 HTML report: {api_dir}/test-results/report.html")


def generate_performance_report():
    """Generate performance test report"""
    api_dir = Path(__file__).parent.parent.parent
    
    print("\nGenerating performance report...")
    
    # Check if locust is available
    try:
        run_command("locust --version", cwd=str(api_dir))
        
        # Generate performance report
        run_command(
            "locust -f tests/performance/locustfile.py --headless --users 10 --spawn-rate 2 --run-time 30s --html=performance-report.html --host http://localhost:8000",
            cwd=str(api_dir)
        )
        
        print("✅ Performance report generated!")
        print(f"📁 Performance report: {api_dir}/performance-report.html")
        
    except Exception as e:
        print(f"⚠️  Performance report generation skipped: {e}")


def main():
    """Main function"""
    print("🚀 Generating comprehensive test reports...")
    
    try:
        generate_coverage_reports()
        generate_test_execution_report()
        generate_performance_report()
        
        print("\n🎉 All reports generated successfully!")
        
    except Exception as e:
        print(f"❌ Error generating reports: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

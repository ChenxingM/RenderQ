"""
RenderQ CLI - 命令行工具
"""
import json
import sys
from datetime import datetime

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

app = typer.Typer(help="RenderQ 渲染队列命令行工具")
console = Console()

# 默认服务器地址
DEFAULT_SERVER = "http://localhost:8000"


def get_client(server: str = None) -> httpx.Client:
    """获取HTTP客户端"""
    return httpx.Client(base_url=server or DEFAULT_SERVER, timeout=30)


# ============ Jobs ============

@app.command()
def submit(
    plugin: str = typer.Option(..., "-p", "--plugin", help="插件类型 (如: aftereffects)"),
    name: str = typer.Option(..., "-n", "--name", help="作业名称"),
    project: str = typer.Option(None, "--project", help="工程文件路径"),
    comp: str = typer.Option(None, "--comp", help="合成名称 (AE)"),
    output: str = typer.Option(None, "--output", help="输出路径"),
    priority: int = typer.Option(50, "--priority", help="优先级 (0-100)"),
    pool: str = typer.Option("default", "--pool", help="Worker池"),
    frame_start: int = typer.Option(None, "-s", "--start", help="起始帧"),
    frame_end: int = typer.Option(None, "-e", "--end", help="结束帧"),
    chunk: int = typer.Option(0, "--chunk", help="分块大小"),
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """提交渲染作业"""
    
    # 构建plugin_data
    plugin_data = {}
    
    if plugin == "aftereffects":
        if not all([project, comp, output]):
            console.print("[red]AE作业需要: --project, --comp, --output[/red]")
            raise typer.Exit(1)
        
        plugin_data = {
            "project_path": project,
            "comp_name": comp,
            "output_path": output,
        }
        
        if frame_start is not None:
            plugin_data["frame_start"] = frame_start
        if frame_end is not None:
            plugin_data["frame_end"] = frame_end
        if chunk > 0:
            plugin_data["chunk_size"] = chunk
    else:
        # 通用参数
        if project:
            plugin_data["project_path"] = project
        if output:
            plugin_data["output_path"] = output
    
    job_data = {
        "name": name,
        "plugin": plugin,
        "priority": priority,
        "pool": pool,
        "plugin_data": plugin_data,
    }
    
    with get_client(server) as client:
        try:
            resp = client.post("/api/jobs", json=job_data)
            resp.raise_for_status()
            job = resp.json()
            console.print(f"[green]✓ 作业已提交[/green]")
            console.print(f"  ID: {job['id']}")
            console.print(f"  名称: {job['name']}")
        except httpx.HTTPStatusError as e:
            console.print(f"[red]提交失败: {e.response.text}[/red]")
            raise typer.Exit(1)


@app.command()
def jobs(
    status: str = typer.Option(None, "-s", "--status", help="筛选状态"),
    limit: int = typer.Option(50, "-l", "--limit", help="显示数量"),
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """列出作业"""
    
    params = {"limit": limit}
    if status:
        params["status"] = status
    
    with get_client(server) as client:
        try:
            resp = client.get("/api/jobs", params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            console.print(f"[red]获取失败: {e}[/red]")
            raise typer.Exit(1)
    
    if not data:
        console.print("[yellow]没有作业[/yellow]")
        return
    
    table = Table(title="作业列表")
    table.add_column("ID", style="dim", width=8)
    table.add_column("名称", style="cyan")
    table.add_column("插件")
    table.add_column("状态")
    table.add_column("进度", justify="right")
    table.add_column("任务")
    table.add_column("优先级", justify="right")
    
    status_colors = {
        "pending": "white",
        "queued": "blue",
        "active": "green",
        "completed": "green bold",
        "failed": "red",
        "suspended": "yellow",
        "cancelled": "dim",
    }
    
    for job in data:
        status = job.get("status", "unknown")
        color = status_colors.get(status, "white")
        
        table.add_row(
            job["id"][:8],
            job["name"],
            job["plugin"],
            f"[{color}]{status}[/{color}]",
            f"{job.get('progress', 0):.1f}%",
            f"{job.get('task_completed', 0)}/{job.get('task_total', 0)}",
            str(job.get("priority", 50)),
        )
    
    console.print(table)


@app.command()
def job(
    job_id: str = typer.Argument(..., help="作业ID"),
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """查看作业详情"""
    
    with get_client(server) as client:
        try:
            resp = client.get(f"/api/jobs/{job_id}")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.print(f"[red]作业不存在: {job_id}[/red]")
            else:
                console.print(f"[red]获取失败: {e}[/red]")
            raise typer.Exit(1)
    
    console.print(f"\n[bold]作业详情[/bold]")
    console.print(f"  ID: {data['id']}")
    console.print(f"  名称: {data['name']}")
    console.print(f"  插件: {data['plugin']}")
    console.print(f"  状态: {data['status']}")
    console.print(f"  进度: {data.get('progress', 0):.1f}%")
    console.print(f"  任务: {data.get('task_completed', 0)}/{data.get('task_total', 0)}")
    console.print(f"  优先级: {data.get('priority', 50)}")
    console.print(f"  提交时间: {data.get('submitted_at', 'N/A')}")
    
    if data.get('error_message'):
        console.print(f"  [red]错误: {data['error_message']}[/red]")
    
    console.print(f"\n[bold]参数:[/bold]")
    console.print(json.dumps(data.get('plugin_data', {}), indent=2, ensure_ascii=False))


@app.command()
def cancel(
    job_id: str = typer.Argument(..., help="作业ID"),
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """取消作业"""
    with get_client(server) as client:
        try:
            resp = client.post(f"/api/jobs/{job_id}/cancel")
            resp.raise_for_status()
            console.print(f"[yellow]✓ 作业已取消: {job_id}[/yellow]")
        except Exception as e:
            console.print(f"[red]取消失败: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def suspend(
    job_id: str = typer.Argument(..., help="作业ID"),
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """暂停作业"""
    with get_client(server) as client:
        try:
            resp = client.post(f"/api/jobs/{job_id}/suspend")
            resp.raise_for_status()
            console.print(f"[yellow]✓ 作业已暂停: {job_id}[/yellow]")
        except Exception as e:
            console.print(f"[red]暂停失败: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def resume(
    job_id: str = typer.Argument(..., help="作业ID"),
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """恢复作业"""
    with get_client(server) as client:
        try:
            resp = client.post(f"/api/jobs/{job_id}/resume")
            resp.raise_for_status()
            console.print(f"[green]✓ 作业已恢复: {job_id}[/green]")
        except Exception as e:
            console.print(f"[red]恢复失败: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def retry(
    job_id: str = typer.Argument(..., help="作业ID"),
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """重试失败的作业"""
    with get_client(server) as client:
        try:
            resp = client.post(f"/api/jobs/{job_id}/retry")
            resp.raise_for_status()
            console.print(f"[green]✓ 作业重试中: {job_id}[/green]")
        except Exception as e:
            console.print(f"[red]重试失败: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def delete(
    job_id: str = typer.Argument(..., help="作业ID"),
    force: bool = typer.Option(False, "-f", "--force", help="强制删除"),
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """删除作业"""
    if not force:
        confirm = typer.confirm(f"确定要删除作业 {job_id} 吗?")
        if not confirm:
            raise typer.Abort()
    
    with get_client(server) as client:
        try:
            resp = client.delete(f"/api/jobs/{job_id}")
            resp.raise_for_status()
            console.print(f"[red]✓ 作业已删除: {job_id}[/red]")
        except Exception as e:
            console.print(f"[red]删除失败: {e}[/red]")
            raise typer.Exit(1)


# ============ Workers ============

@app.command()
def workers(
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """列出Worker节点"""
    
    with get_client(server) as client:
        try:
            resp = client.get("/api/workers")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            console.print(f"[red]获取失败: {e}[/red]")
            raise typer.Exit(1)
    
    if not data:
        console.print("[yellow]没有Worker[/yellow]")
        return
    
    table = Table(title="Worker列表")
    table.add_column("名称", style="cyan")
    table.add_column("状态")
    table.add_column("当前任务", width=10)
    table.add_column("CPU", justify="right")
    table.add_column("内存", justify="right")
    table.add_column("IP")
    
    status_colors = {
        "idle": "green",
        "busy": "yellow",
        "offline": "dim",
        "disabled": "red",
    }
    
    for w in data:
        status = w.get("status", "offline")
        color = status_colors.get(status, "white")
        
        current = w.get("current_task", "")
        if current:
            current = current[:8]
        
        mem_used = w.get("memory_used", 0) / (1024**3)
        mem_total = w.get("memory_total", 0) / (1024**3)
        
        table.add_row(
            w["name"],
            f"[{color}]{status}[/{color}]",
            current or "-",
            f"{w.get('cpu_usage', 0):.0f}%",
            f"{mem_used:.1f}/{mem_total:.1f}GB",
            w.get("ip_address", "-"),
        )
    
    console.print(table)


# ============ Plugins ============

@app.command()
def plugins(
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """列出可用插件"""
    
    with get_client(server) as client:
        try:
            resp = client.get("/api/plugins")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            console.print(f"[red]获取失败: {e}[/red]")
            raise typer.Exit(1)
    
    table = Table(title="可用插件")
    table.add_column("名称", style="cyan")
    table.add_column("显示名称")
    table.add_column("版本")
    table.add_column("描述")
    
    for p in data:
        table.add_row(
            p["name"],
            p.get("display_name", ""),
            p.get("version", ""),
            p.get("description", ""),
        )
    
    console.print(table)


# ============ Stats ============

@app.command()
def stats(
    server: str = typer.Option(DEFAULT_SERVER, "--server", help="服务器地址"),
):
    """显示系统统计"""
    
    with get_client(server) as client:
        try:
            resp = client.get("/api/stats")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            console.print(f"[red]获取失败: {e}[/red]")
            raise typer.Exit(1)
    
    console.print("\n[bold]系统统计[/bold]\n")
    
    jobs = data.get("jobs", {})
    console.print("[cyan]作业:[/cyan]")
    for status, count in jobs.items():
        console.print(f"  {status}: {count}")
    
    workers = data.get("workers", {})
    console.print("\n[cyan]Worker:[/cyan]")
    for status, count in workers.items():
        console.print(f"  {status}: {count}")


def main():
    app()


if __name__ == "__main__":
    main()

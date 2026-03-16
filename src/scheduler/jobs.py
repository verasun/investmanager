"""Job scheduler using APScheduler."""

from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.job import Job
from loguru import logger


class ScheduleType(Enum):
    """Schedule type enumeration."""

    INTERVAL = "interval"
    CRON = "cron"
    DATE = "date"


class JobScheduler:
    """
    Job scheduler for automated tasks.

    Wraps APScheduler for easy task scheduling.
    """

    def __init__(self):
        """Initialize job scheduler."""
        self.scheduler = BackgroundScheduler()
        self._jobs: dict[str, Job] = {}
        self._is_running = False

    def start(self) -> None:
        """Start the scheduler."""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("Job scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._is_running:
            self.scheduler.shutdown()
            self._is_running = False
            logger.info("Job scheduler stopped")

    def add_interval_job(
        self,
        func: Callable,
        job_id: str,
        *,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        replace_existing: bool = True,
        **kwargs,
    ) -> Job:
        """
        Add an interval-based job.

        Args:
            func: Function to execute
            job_id: Unique job identifier
            seconds: Interval in seconds
            minutes: Interval in minutes
            hours: Interval in hours
            start_date: When to start
            end_date: When to end
            replace_existing: Replace if job exists
            **kwargs: Additional arguments for the function

        Returns:
            Scheduled job
        """
        trigger = IntervalTrigger(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            start_date=start_date,
            end_date=end_date,
        )

        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            kwargs=kwargs,
            replace_existing=replace_existing,
        )

        self._jobs[job_id] = job
        logger.info(f"Added interval job: {job_id}")
        return job

    def add_cron_job(
        self,
        func: Callable,
        job_id: str,
        *,
        hour: Optional[int] = None,
        minute: Optional[int] = None,
        day_of_week: Optional[str] = None,
        day_of_month: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        replace_existing: bool = True,
        **kwargs,
    ) -> Job:
        """
        Add a cron-based job.

        Args:
            func: Function to execute
            job_id: Unique job identifier
            hour: Hour (0-23)
            minute: Minute (0-59)
            day_of_week: Day of week (mon,tue,wed,thu,fri,sat,sun)
            day_of_month: Day of month (1-31)
            start_date: When to start
            end_date: When to end
            replace_existing: Replace if job exists
            **kwargs: Additional arguments for the function

        Returns:
            Scheduled job
        """
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
            day=day_of_month,
            start_date=start_date,
            end_date=end_date,
        )

        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            kwargs=kwargs,
            replace_existing=replace_existing,
        )

        self._jobs[job_id] = job
        logger.info(f"Added cron job: {job_id}")
        return job

    def add_daily_job(
        self,
        func: Callable,
        job_id: str,
        hour: int = 9,
        minute: int = 30,
        **kwargs,
    ) -> Job:
        """
        Add a daily job.

        Args:
            func: Function to execute
            job_id: Unique job identifier
            hour: Hour to run (default 9)
            minute: Minute to run (default 30)
            **kwargs: Additional arguments

        Returns:
            Scheduled job
        """
        return self.add_cron_job(
            func,
            job_id,
            hour=hour,
            minute=minute,
            day_of_week="mon-fri",
            **kwargs,
        )

    def add_weekly_job(
        self,
        func: Callable,
        job_id: str,
        day_of_week: str = "mon",
        hour: int = 9,
        minute: int = 0,
        **kwargs,
    ) -> Job:
        """
        Add a weekly job.

        Args:
            func: Function to execute
            job_id: Unique job identifier
            day_of_week: Day to run (mon, tue, etc.)
            hour: Hour to run
            minute: Minute to run
            **kwargs: Additional arguments

        Returns:
            Scheduled job
        """
        return self.add_cron_job(
            func,
            job_id,
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
            **kwargs,
        )

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job.

        Args:
            job_id: Job identifier

        Returns:
            True if removed, False if not found
        """
        if job_id in self._jobs:
            self.scheduler.remove_job(job_id)
            del self._jobs[job_id]
            logger.info(f"Removed job: {job_id}")
            return True
        return False

    def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        if job_id in self._jobs:
            self.scheduler.pause_job(job_id)
            logger.info(f"Paused job: {job_id}")
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        if job_id in self._jobs:
            self.scheduler.resume_job(job_id)
            logger.info(f"Resumed job: {job_id}")
            return True
        return False

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[dict]:
        """
        Get all scheduled jobs.

        Returns:
            List of job info dictionaries
        """
        jobs = []

        for job_id, job in self._jobs.items():
            jobs.append(
                {
                    "id": job_id,
                    "func": str(job.func),
                    "trigger": str(job.trigger),
                    "next_run": job.next_run_time,
                    "pending": job.pending,
                }
            )

        return jobs

    def run_job_now(self, job_id: str) -> bool:
        """
        Execute a job immediately.

        Args:
            job_id: Job identifier

        Returns:
            True if executed, False if not found
        """
        job = self._jobs.get(job_id)
        if job:
            job.modify(next_run_time=datetime.now())
            logger.info(f"Triggered immediate run for job: {job_id}")
            return True
        return False


# Common scheduled jobs
class ScheduledTasks:
    """Predefined scheduled tasks."""

    def __init__(self, scheduler: JobScheduler):
        """Initialize with scheduler."""
        self.scheduler = scheduler

    def setup_daily_market_update(
        self,
        data_fetch_func: Callable,
        notification_func: Optional[Callable] = None,
    ) -> Job:
        """
        Set up daily market data update.

        Args:
            data_fetch_func: Function to fetch market data
            notification_func: Optional notification function

        Returns:
            Scheduled job
        """
        def update_market_data():
            logger.info("Running daily market update...")
            data = data_fetch_func()
            if notification_func:
                notification_func(data)
            return data

        return self.scheduler.add_daily_job(
            update_market_data,
            "daily_market_update",
            hour=15,
            minute=30,
        )

    def setup_daily_report(
        self,
        report_func: Callable,
        notification_func: Optional[Callable] = None,
    ) -> Job:
        """
        Set up daily report generation.

        Args:
            report_func: Function to generate report
            notification_func: Optional notification function

        Returns:
            Scheduled job
        """
        def generate_daily_report():
            logger.info("Generating daily report...")
            report = report_func()
            if notification_func:
                notification_func(report)
            return report

        return self.scheduler.add_daily_job(
            generate_daily_report,
            "daily_report",
            hour=17,
            minute=0,
        )

    def setup_risk_monitoring(
        self,
        risk_check_func: Callable,
        interval_minutes: int = 5,
    ) -> Job:
        """
        Set up risk monitoring job.

        Args:
            risk_check_func: Function to check risk
            interval_minutes: Check interval in minutes

        Returns:
            Scheduled job
        """
        return self.scheduler.add_interval_job(
            risk_check_func,
            "risk_monitoring",
            minutes=interval_minutes,
        )

    def setup_data_refresh(
        self,
        refresh_func: Callable,
        interval_minutes: int = 15,
    ) -> Job:
        """
        Set up data refresh job.

        Args:
            refresh_func: Function to refresh data
            interval_minutes: Refresh interval in minutes

        Returns:
            Scheduled job
        """
        return self.scheduler.add_interval_job(
            refresh_func,
            "data_refresh",
            minutes=interval_minutes,
        )
import time, os, argparse

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import config
from src.pipeline.pipeline import ImportPipeline
from src.scraping.scraper import Scraper
from src.utils.logging import init_logging, get_logger
from src.utils.tools import call_with_exponential_backoff
from src.notification.notification_center import NotificationCenter


def scraping_task(full_scrape: bool):
    init_logging()
    logger = get_logger('scraper.scheduler')
    def scrape():
        logger.info("Initiating scraping task")
        try:
            scraper = Scraper(scrape_all=full_scrape)
            pipeline = ImportPipeline()

            for target_url in config.scraping.TARGET_URLS:
                chunks = scraper.scrape_target(target_url)
                pipeline.import_from_scraper(chunks)
                scraper.delete_temp_merged_chunks(target_url)

            logger.info("Scraper task finished gracefully")
        except Exception as e:
            logger.error(f"Scraping task was interrupted: {e}")
            raise e

    result = call_with_exponential_backoff(scrape)

    if result['status'] == 'FAIL':
        center = NotificationCenter()
        center.send_error(
            "ERROR: Scraping failed",
            f"Scraping procedure failed after {config.scraping.MAX_RETRIES} attempts with message: {result['last_error']}",     
            "email",
            [
                os.path.join(config.paths.LOGS, 'scraping.log')
            ]
        )
        raise result['last_error']


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--init_sched', action='store_true')
    parser.add_argument('--full_scrape', action='store_true')
    return parser.parse_args()


def run_scheduler():
    scheduler = BackgroundScheduler()

    # Daily at 3 AM (Mon–Sat)
    scheduler.add_job(
        scraping_task,
        trigger=CronTrigger(day_of_week='mon-sat', hour=3, minute=0),
        args=[False],
        id='daily_scrape',
        max_instances=1,   
        coalesce=True,
        misfire_grace_time=3600,
    )

    # Sunday at 2 AM (full scrape)
    scheduler.add_job(
        scraping_task,
        trigger=CronTrigger(day_of_week='sun', hour=2, minute=0),
        args=[True],
        id='weekly_full_scrape',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    print("Scheduler started")

    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Scheduler stopped")


if __name__ == "__main__":
    args = parse_args()

    if args.init_sched:
        run_scheduler()
    else:
        scraping_task(args.full_scrape)

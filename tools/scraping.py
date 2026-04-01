import argparse 
from apscheduler import Scheduler, task

from src.config import config
from src.pipeline.pipeline import ImportPipeline
from src.scraping.scraper import Scraper 
from src.utils.logging import init_logging, get_logger

init_logging() 
logger = get_logger('scraper.scheduler')


@task(max_running_jobs=1)
def scraping_task(full_scrape: bool):
    logger.info("Initiating scraping task")
    while True:
        try:
            scraper = Scraper(scrape_all=full_scrape)
            pipeline = ImportPipeline()

            for target_url in config.scraping.TARGET_URLS:
                chunks = scraper.scrape_target(target_url)
                pipeline.import_from_scraper(chunks)
            
            logger.info("Scraper task finished gracefully")
            return
        except Exception as e:
            logger.error(f"Scraping task was interrupted: {e}")
            continue


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--init_sched',  action='store_true')
    parser.add_argument('--stop_sched',  action='store_true')
    parser.add_argument('--full_scrape', action='store_true')
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    if args.stop_sched:
        with Scheduler() as scheduler:
            scheduler.remove_schedule('daily_scrape')
            logger.info("Deleted schedule 'Daily Scrape'")
            scheduler.remove_schedule('weekly_full_scrape')
            logger.info("Deleted schedule 'Weekly Full Scrape'")
        exit()

    if args.init_sched:
        with Scheduler() as scheduler:
            scheduler.configure_task(
                'scraper_task',
                func=scraping_task,
                job_executor='threadpool',
            )
            logger.info("Configured scheduler task for scraping")

            # Daily at 3 AM only prioritized pages
            scheduler.add_schedule(
                id='daily_scrape',
                task_id='scraper_task',
                trigger='cron',
                day_of_week='mon-sat',
                hour=3,
                minute=0,
                args=[False],
            )
            logger.info("Added schedule 'Daily Scrape'")

            # b) Every Sunday 2 AM full scrape + validation
            scheduler.add_schedule(
                id='weekly_full_scrape',
                task_id='scraper_task',
                trigger='cron',
                day_of_week='sun',
                hour=2,
                minute=0,
                args=[True],
            )
            logger.info("Added schedule 'Weekly Full Scrape'")

            scheduler.start()
            logger.info("Scheduler initialized")
        exit()

    scraping_task(args.full_scrape)

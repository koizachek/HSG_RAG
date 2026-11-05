import uat_override, sys
sys.argv = ["update_programme_facts", "--dry-run"]
from src.pipeline.update_programme_facts import main
sys.exit(main())

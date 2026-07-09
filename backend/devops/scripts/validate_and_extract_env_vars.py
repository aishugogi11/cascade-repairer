import yaml
import sys
import os

# define required top-level keys and required keys inside build_env_vars
REQUIRED_TOP_LEVEL_KEYS = {"build_env_vars"}
REQUIRED_ENV_VARS = {"IMAGE_NAME", "TARGET_AR", "VERSION", "GCP_LOCATION"}
OPTIONAL_ENV_VARS = {"PUSHOVER_USER", "PUSHOVER_TOKEN"}


def validate_and_extract_env_vars(config_path="config.yaml", output_path="image.env"):
    if not os.path.exists(config_path):
        print(f"Error: Configuration file '{config_path}' does not exist.")
        sys.exit(1)

    try:
        with open(config_path, "r") as file:
            config = yaml.safe_load(file)

        # validate top-level keys
        for key in REQUIRED_TOP_LEVEL_KEYS:
            if key not in config:
                print(
                    f"Error: Missing required top-level key '{key}' in configuration."
                )
                sys.exit(1)

        build_env_vars = config.get("build_env_vars", {})

        # validate required keys inside build_env_vars
        for key in REQUIRED_ENV_VARS:
            if key not in build_env_vars:
                print(
                    f"Error: Missing required environment variable '{key}' in 'build_env_vars'."
                )
                sys.exit(1)

        # write the environment variables to the output file
        with open(output_path, "w") as env_file:
            # Write build_env_vars
            for key, value in build_env_vars.items():
                env_file.write(f"{key}={value}\n")

            # Add optional environment variables if they exist
            for key in OPTIONAL_ENV_VARS:
                if key in build_env_vars:
                    env_file.write(f"{key}={build_env_vars[key]}\n")

            # Extract and write metadata variables (for BigQuery table setup)
            metadata = config.get("metadata", {})
            for key, value in metadata.items():
                # Convert to uppercase with METADATA_ prefix
                env_key = f"METADATA_{key.upper()}"
                env_file.write(f"{env_key}={value}\n")

            # Add SHORT_SHA from Cloud Build environment or generate from git
            short_sha = os.environ.get('SHORT_SHA', '')
            if not short_sha:
                # Fallback: get from git if not in Cloud Build environment
                try:
                    import subprocess
                    result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                                          capture_output=True, text=True, check=True)
                    short_sha = result.stdout.strip()
                except:
                    short_sha = 'latest'  # Ultimate fallback

            env_file.write(f"SHORT_SHA={short_sha}\n")

        print(f"Environment variables successfully written to '{output_path}'.")

    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


# execute the function if this script is run directly
validate_and_extract_env_vars()

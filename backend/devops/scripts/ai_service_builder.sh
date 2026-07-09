#!/bin/bash

script_path=$(realpath "$0" | sed 's|\(.*\)/.*|\1|')
source $script_path/logging.sh 

assert_file() {
    if [ ! -f "$1" ]; then
        log_error "File $1 does not exist."
        exit 1
    fi
}



# FUNCTIONS 

function build_one() {
    local GCP_LOCATION=$1
    local PROJECT_ID=$2
    local IMAGE_NAME=$3
    local TARGET_AR=$4
    local SHORT_SHA=$5
    local VERSION=$6
    local VERBOSE=$7


    if [ ! -f Dockerfile ]; then
        log_error "NO DOCKERFILE FOR $IMAGE_NAME"
        return 1;
    fi

    BASE_FULL_IMAGE_NAME=$(echo "$GCP_LOCATION-docker.pkg.dev/$PROJECT_ID/$TARGET_AR/$IMAGE_NAME")
    LASTEST_TAGGED=$(echo "$BASE_FULL_IMAGE_NAME:latest")
    SHA_TAGGED=$(echo "$BASE_FULL_IMAGE_NAME:$SHORT_SHA")
    VERSION_TAGGED=$(echo "$BASE_FULL_IMAGE_NAME:$VERSION")
    log_info "Building image $IMAGE_NAME -> $BASE_FULL_IMAGE_NAME"


    log_info "START: Building $BASE_FULL_IMAGE_NAME" 

    docker build -t $LASTEST_TAGGED .

    docker tag $LASTEST_TAGGED $SHA_TAGGED
    log_info "Tagged SHA: $SHA_TAGGED"

    docker tag $LASTEST_TAGGED $VERSION_TAGGED
    log_info "Tagged VERSION: $VERSION_TAGGED"
    
    log_info "Verifying tagged images exist:"
    docker images | grep $IMAGE_NAME

    log_info "PUSHING to $PROJECT_ID/$TARGET_AR"
    log_info "Pushing LATEST: $LASTEST_TAGGED"
    if docker push $LASTEST_TAGGED; then
        log_info "✅ LATEST push successful"
    else
        log_error "❌ LATEST push failed"
        return 1
    fi
    
    log_info "Pushing SHA: $SHA_TAGGED"
    if docker push $SHA_TAGGED; then
        log_info "✅ SHA push successful"
    else
        log_error "❌ SHA push failed"
        return 1
    fi
    
    log_info "Pushing VERSION: $VERSION_TAGGED"
    if docker push $VERSION_TAGGED; then
        log_info "✅ VERSION push successful"
    else
        log_error "❌ VERSION push failed"
        return 1
    fi

    log_info "✅ ALL PUSHES SUCCESSFUL for $IMAGE_NAME to $PROJECT_ID/$TARGET_AR" 
    log_info "Tagged and Pushed: $LASTEST_TAGGED, $SHA_TAGGED, $VERSION_TAGGED"
    
    log_info "Verifying images in registry:"
    gcloud artifacts docker images list $GCP_LOCATION-docker.pkg.dev/$PROJECT_ID/$TARGET_AR/$IMAGE_NAME --limit=10 || true
}



function main() {
    local CLOUDBUILD_LOCATION=$1 # NOTE NOT USING THIS RIGHT NOW 
    local PROJECT_ID=$2
    local SHORT_SHA=$3
    assert_file "image.env"
    set -a 
    source image.env
    set +a

    : "$(TARGET_AR:?TARGET_AR is not set or empty)"
    : "$(VERSION:?VERSION is not set or empty)"
    : "${IMAGE_NAME:?IMAGE_NAME is not set or empty}"
    : "${GCP_LOCATION:?GCP_LOCATION is not set or empty}"

    build_one "$GCP_LOCATION" "$PROJECT_ID" "$IMAGE_NAME" "$TARGET_AR" "$SHORT_SHA" "$VERSION" "$VERBOSE"

}

main "$@"
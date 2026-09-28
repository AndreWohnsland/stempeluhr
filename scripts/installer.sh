#!/bin/bash
# installer script for the application
# mostly used for linux os
# desktop at: https://github.com/AndreWohnsland/Stempeluhr/blob/master/scripts/stempeluhr.desktop
# icon at: https://github.com/AndreWohnsland/Stempeluhr/blob/master/stempeluhr/ui/clock.png

# retuns the latest release tag
get_latest_release_tag() {
  curl -L \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    https://api.github.com/repos/AndreWohnsland/Stempeluhr/releases/latest |
    grep '"tag_name":' |
    sed -E 's/.*"([^"]+)".*/\1/'
}

# download the latest release for the corresponding os
download_latest_release() {
  sudo curl -L -o /usr/bin/stempeluhr https://github.com/AndreWohnsland/Stempeluhr/releases/latest/download/stempeluhr_ubuntu
  sudo curl -o /usr/share/pixmaps/stempeluhr.png https://raw.githubusercontent.com/AndreWohnsland/Stempeluhr/master/stempeluhr/ui/clock.png
  sudo curl -o /usr/share/applications/stempeluhr.desktop https://raw.githubusercontent.com/AndreWohnsland/Stempeluhr/master/scripts/stempeluhr.desktop
}

# install the application
install() {
  download_latest_release
  sudo chmod +x /usr/bin/stempeluhr
}

# execute the installer
install

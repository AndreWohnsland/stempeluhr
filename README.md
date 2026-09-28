# Stempeluhr

> *Stempeluhr* (pronounced SHTEM-pel-oor, [ˈʃtɛmpl̩ˌʔuːɐ̯]) is German for *punch clock* — the clock at the factory gate that workers used to stamp their arrival and leaving times onto a time card. This app is that clock, minus the cardboard.

A Qt-Application to start and stop time tracking, enter additional breaks, view your daily and monthly data, and generate a report out of it.

![mainwindow](https://raw.githubusercontent.com/AndreWohnsland/Stempeluhr/master/doc/mainwindow.PNG 'mainwindow')
![report](https://raw.githubusercontent.com/AndreWohnsland/Stempeluhr/master/doc/report.PNG 'report')

## Installation

The easiest way is installing from PyPI, otherwise you can use the standalone version.

### A: Install from PyPI (recommended)

The app is published on PyPI as [`stempeluhr`](https://pypi.org/project/stempeluhr/).
Install it as a tool with [uv](https://docs.astral.sh/uv/getting-started/installation/) (or use `pipx` if you prefer):

```bash
uv tool install stempeluhr
stempeluhr
```

This is especially recommended on macOS, where the standalone binary is not signed and gets blocked by Gatekeeper.
Update any time with:

```bash
uv tool upgrade stempeluhr
```

### B: Standalone Installation

With a new release, there is also a standalone version available.
You can download the latest release from the [release page](https://github.com/AndreWohnsland/Stempeluhr/releases).
Choose the right version for your operating system and download the file.
Execute the file according to your usual system start option.
The application will start and you can use it as described below.

#### Windows

Just use the installer, put it on the desktop, and start the application via the icon.

#### Linux

You probably know your ways how to get started with the binary file.
But if you are lazy like me, you can install the application with the [following script](https://github.com/AndreWohnsland/Stempeluhr/blob/master/scripts/installer.sh):

```bash
curl -s https://raw.githubusercontent.com/AndreWohnsland/Stempeluhr/master/scripts/installer.sh | bash
```

This will download the latest release, put it into your binary folder, and create an application entry.

#### macOS

This is currently still experimental, but you can try either the manual installation or the standalone version.

### B: Manual Installation

We use [uv](https://docs.astral.sh/uv/getting-started/installation/) for managing Python versions and packages.
First clone the repository and cd into it.
To start the app, you run the `runme.py` file, you can create a shortcut on your desktop:

```bash
git clone https://github.com/AndreWohnsland/Stempeluhr.git
cd Stempeluhr
uv sync
uv run runme.py
```

If you want to contribute, also install the [pre-commit](https://pre-commit.com/) hooks, they run linting and formatting before each commit:

```bash
uv run pre-commit install
```

### Manual build of the standalone version

If you want to build the standalone version by yourself, you can also do it with [uv](https://docs.astral.sh/uv/getting-started/installation/).
Especially on windows and macOS, because on these systems, they will probably complain that the downloaded binary is not trusted.
First, make sure you have uv installed and clone the repository.
Then run the following commands to create the standalone version:

```bash
uv run pyinstaller installer.spec
```

The created binary will be in the `dist` folder.

## Options

On first startup, the application will create the needed configuration and the database.
You can adjust your settings via `Options > Configure Settings` and the folder to save the reports to with `Options > Set Save folder`.
With `Start` the tracking is started and with `Stop` the tracking is stopped.
You can repeat this start-stop procedure any time you want.
Over the spin box you can select the pause time and submit them with the `Pause` button.
It is also possible to enter negative Pause to correct previous mistakes.
You can also start and stop over the tray icon in the taskbar.

![settings](https://raw.githubusercontent.com/AndreWohnsland/Stempeluhr/master/doc/options.PNG 'settings')

## Reports

An overview can be seen when clicking `Options > Summary`.
With a datepicker, a day can be chosen to display a summary of the data in either the according month or all events of this day.
The day / month view can be changed over the view toggle button.
To generate the report of your overtime or work time, click the `Export` button.
By default settings, the report will be saved into the reports folder of this application.
As soon as the save folder was changed over the option setting, the app will use this location instead.
The default work time for overtime is eight hours, time worked less than eight will displayed as zero overtime.
The overtime/work time is rounded to the closest quarter hour.
Breaks are already subtracted in the calculation, adherence to the regular break times is not observed.

## Adjust Past Values

To enter values you have missed, you can switch to past entry mode.
This can be done over the `Options > Switch to Past Entry` setting.
A date and time can be selected with the according action to insert past values.
To go back to the default option, click the shown back button.

## Updating to latest Version

Just download the latest executable from the [release page](https://github.com/AndreWohnsland/Stempeluhr/releases).
If you have installed the application manually, you can update it with git:

```bash
git pull
uv sync
```

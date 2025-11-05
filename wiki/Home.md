# Welcome to the Huntsman Project!

In this wiki you will find a few helpful hints to get you started in the Huntsman world of software development, including Github help, python tips, and a wealth of other handy bits and pieces that have been gathered by spiderlings over the years. 

## Important Note 
**If you sudo reboot Huntsman, you must also do a power cycle via the NPS!** The fitlet will not recover from sudo reboot and will hang indefinitely - so grab the NPS IP and password from the important docs, turn off the control computer power for a least 30 seconds, then switch back on.

## Getting Started

There are a few things to download before you get started. If you haven't already, get yourself a [Github account](https://github.com/). This is where you will find the repository containing all of the Huntsman project software in development. 

If you are new to python, depending on what operating system you are using, there are many ways to develop in python. A great package and environment manager is [Anaconda](https://www.anaconda.com/what-is-anaconda/). This operates as a gateway to Spyder, Jupyter Notebooks, RStudio and much more. Another great one is [Atom](https://atom.io/). Shop around and find one which is most comfortable for you. 

### Prerequisites

You may also have to download a few programs and packages. Pip, Homebrew and Conda are all essential when downloading and installing packages. To install these, start by opening up the terminal and installing homebrew: 

```
$ /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
```
Now you can use [Homebrew](https://brew.sh/) to install the latest version of python (if you haven't already). The easiest way to check what version of python you are running it to type:

```
$ python -V
```
If you find that you need to install the latest version, python 3, then type:

```
$ brew install python3
```
With python now installed, you can easily run:

```
$ sudo easy_install pip
```

Pip is now installed and can be used to install any other external packages or clone repositories that you need. You may also want to take the time now to install XCode command lines tools. 

```
$ xcode-select --install
```

Should anything ever go wrong, you can always ask the doctor!

```
$ brew doctor
```

POCS uses [FPACK](https://heasarc.gsfc.nasa.gov/fitsio/fpack/) to compress raw images. Here is how you compile the relevant binaries:

```
brew uninstall cfitsio
curl "https://heasarc.gsfc.nasa.gov/FTP/software/fitsio/c/cfitsio_latest.tar.gz" -o cfitsio_latest.tar.gz
tar xzvf cfitsio_latest.tar.gz
cd cfitsio-3\t
./configure --prefix=/usr/local
make
make fpack
make funpack
make install
```

### GitKraken

GitKraken is the easiest way to manage your development environment, by providing a very handy GUI for creating branches, pushing code from your local copy of the repo to the remote, and pulling down changes. You can learn all about this system [here](http://nvie.com/posts/a-successful-git-branching-model/ ). 

### The Basics 

In short, navigate to the Repo Managment tab of GitKraken and clone the repo by pasting ```https://github.com/AstroHuntsman/huntsman-pocs.git``` into the 'Clone a Repo' URL section. Choose a directory to clone to, and the entire AstoHuntsman repo will be cloned here. You will notice there is now a local and a remote copy of the repo. Any changes you make to the files in the clone on your computer will be recognised by GitKraken and displayed. These local changes can then be pushed to the remote copy on GitHub, by selecting push. 
Other spiderlings may also be developing at the same time, so it is good practice to regularly pull changes from the remote copy to your local copy to ensure you are not missing anything.

>  Note: GitKraken will warn you before you do anything permanent. As long as you work on your own branch, there is very little that can go badly wrong!

### Branching

Before you change anything in the repo, always make your own branch. This will ensure any changes that you make can be reviewed, tried and tested before any permanent changes are made. This also protects the repo from anything bad happening! Create a new branch off the develop branch, and GitKraken will do the rest. You can switch between branches by checking in and out of the local versions of your branch. When you are happy with your changes, commit those that you want to keep, and then push them to GitHub. 

> Note: It's always best to push your code when it's not broken. If you are still unhappy at the end of the day but want to save it somewhere for safe keeping, create a local copy in a new directory. You can never have too many backups! 

To make your own branch, first `fork` the repo. If you have not done that, it is needed to add your computer SSH key to your GitHub profile before you clone the repo to your computer. You are able to reach this SSH key by following commands:

`$ ssh-keygen`

`$ cat .ssh/id_rsa.pub`

When you ran the above command, the SSH key will be showed in the terminal. Then on your GitHub profile, `setting>SSH and GPG keys`, create a new SSH key and paste the SSH key there. 

Then you should clone the forked repo to your computer:

`$ git clone git@github.com:your_profile_name/repository_name.git`

If you can not 

To link your local repo to that of the main repository you have to run the following while you are in the repository environment:

`$ git remote add --tags upstream git@github.com:main_repository_profile/repository_name.git`

To make sure it is happened, type:

`$ git remote -v`

To see branches, and the branch that you are in, type the following command:

`$ git branch`

And to change your branch or create a new one, respectively run these lines:

`$ git checkout branch_name`

`$ git checkout -b new_branch_name upstream/main_branch_name`

In case of facing the following error:

`$ fatal: 'upstream/main_branch_name' is not a commit and a branch 'new_branch_name' can not be created from it`

Try:

`$ git fetch upstream`

And then create your new branch.

## GitHub
GitHub is where all the magic happens, so make use of all of its features. 

**A word about important things and GitHub**

1. Don’t put sensitive information on public repos like IP addresses! Enough said. 

2. Backup everything multiply times. GitKraken is amazing, but not perfect. It's better to be safe with multiple copies of everything than to lose all your work. 

### Pull Requests 

Don't be afraid to make a pull request early. You may find the tips and hints from a PR is the best way develop your python skills. The pull request is the review stage before your own branch (and **ALL** of the changes you have made to any file in this branch) will be merged with the master development branch. 
> Note: Github will keep track of all the changes you have made before merging occurs. If you are making big changes to several files, then it is best to open several pull requests on seperate branches for each change. This ensures PR's are kept small and manageable and all changes can be tracked.  

### Code Reviews

Reviewing each others code not only provides constructive critisism for the developer, but it also helps you to spot and make changes in your own code. Keeping track of an open PR helps give direction when debugging or simply making your code more efficient. Often times the comments made by others will prevent you hitting a mental brick wall.  
 
### Slack & Trello

Slack is the Huntsman collaboration space. Note only does it help keep a history of suggestions, hints and tips, but it makes sharing files and ideas a breeze. Sign up for free [here](https://slack.com). Trello is a nice addition to slack, which is kept as an open job board. If you find yourself stuck and looking for something to do, there is always a job open here that can be taken on board. You can find trello [here](https://trello.com/).

## Getting started in the world of Python 

A word of advice. You will often find that the function you have been working on for the past 3 hours has already been created. Make sure to search around online and in the Repo before embarking on reinventing the wheel. You will find that Stackoverflow is your best friend, and the value of copy and pasting error messages into google cannot be stressed enough. Someone will always have encountered your problem before (or one like it) so before stressing, do a quick google search. And remember, answers **do exist** beyond page 1 of the results. 

The best practice is not to hard code too many things. It’s easier and more user friendly to create lots of small, flexible functions than one big script that does everything. Break the problem up into a road map of smaller steps (and functions) to complete, and make use of everything python has to offer: dictionaries, functions even classes. You’ll often find what you want to do will fit nicely into one of these categories, so don't try to fit a triangular shaped block into a square hole. 

If you haven’t already, learn how to make the most of the command line. It is often the most pain free way of managing anything.

<details>
<summary>Want some extra hand tips to start out with? Click here! </summary>
<br>
Installing packages from a GitHub repo is easy with pip. To install a package like Gunagala, simply input:

```
$ pip install git+https://github.com/AstroHuntsman/gunagala.git
```
To install any package, replace the last command with *git+'your web URL'*
</details>

### Documentation and Formatting
It is essential to write detailed docstrings. This not only helps others understand and use your code, but it will help you coming back to it a week later. Docstrings can even be called by inputing:

```python
help('ClassName')
```
If you have never seen that class before, this will return all of the attributes, methods and bit and pieces stored in that class. The standard Huntsman uses for writing docstrings can be found [here](http://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html). A more complete reference for the google developer documentation style [can be found here](https://developers.google.com/style/highlights).  

It is also important to correctly format your code for ease of reading. [Pep8](https://www.python.org/dev/peps/pep-0008/) is the style guide for Python code and it is very easy to conform too, with the help of a few packages. Atom has built in Pep8 formatting, but if you are using Anaconda Navigator with an editor like Spyder or Jupyter, then Autopep8 is probably for you. 

```
$ pip install --upgrade autopep8
```
Navigate to the directory where your file is being kept and then run:

```
$ autopep8 --in-place --aggressive --aggressive <filename>
```
If you get stuck, check out the [full documentation](https://pypi.python.org/pypi/autopep8) for Autopep8 

## Testing

*A more extensive introduction to python testing is coming - watch this space*

Testing your code is absolutely essential, and it's best to do it earlier on before the problems get too out of hand. Understanding what could go wrong and all the possible errors that your code could give will force you to have a better understanding of what it is capable of. 

What kind of wrong values could you give it? And how will you deal with the error messages should this occur. Always think about the user, navigating your code for the first time. Aim for high coverage in your tests, by implementing all methods, function *and* all possible options in your methods. 

To get started make sure this call works: 

```
$ python3 setup.py test
```

### Pytest

[Pytest](https://docs.pytest.org/en/latest/) is a python testing tool designed to allow you to write unit tests for your code. The beauty of these is that you can write tests that skip known broken sections, and test parts of your code even when hardware is required for full functionality. 

Make test functions as simple as possible so you don't make mistakes in them. It's best to write lots of little ones, so you can pinpoint the sources of error when you run them. You can also make use of fixtures. This will allow you to place everything you need to set up the code for a test in one place, and reproduce a single object like a Camera() many times, even with some differences via parameters. You can also also produce slightly different versions by sending in multiple parameters into the fixture. Check out the full [pytest documentation](https://docs.pytest.org/en/latest/contents.html#toc) for an extensive record of all the features pytest has to offer.

<details>
<summary>Here's an example of a pytest fixture in use. </summary>
Always start the test code with importing pytest, followed by any modules need in the test, and of course the module you are testing. In this example, we are testing the Huntsman utils hdr code.

Pytest fixture has been used here to create an instance of the create_imagers class. It can also be noted that scope has been set to session, and so the instance will be used for every test in that session.   
<br>

```python
import pytest
import astropy.units as u
from astropy.coordinates import SkyCoord
from gunagala.imager import create_imagers
from huntsman.utils import hdr

@pytest.fixture(scope='session')
def imagers():
    return create_imagers()

def test_target_list(imagers):
    name = 'M6 Toll'
    base = SkyCoord("16h52m42.2s -38d37m12s")

    for imager_name in imagers:
        for filter_name in imagers[imager_name].filters:
            exposure_parameters = {'filter_name': filter_name,
                                   'shortest_exp_time': 5 * u.second,
                                   'longest_exp_time': 600 * u.second,
                                   'num_long_exp': 1,
                                   'exp_time_ratio': 2.0,
                                   'snr_target': 5.0}
            targets = hdr.get_target_list(target_name=name,
                                          imagers=imagers,
                                          primary_imager=imager_name,
                                          base_position=base,
                                          exposure_parameters=exposure_parameters)

            assert targets
```
Should something not exist, for example a piece of hardware needs to be connected in order to test the code, then pytest.skip can be used, to skip that test in the session. In this particular example, if we don't find any targets, an assertion error will be given by pytest.  
</details> 

Remember to always name your test files as test_.py into a subdirectory named 'test'.



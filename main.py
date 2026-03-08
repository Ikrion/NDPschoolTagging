# This is a sample Python script.
import dataProcessing


# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print("Welcome to the NDP School tagging program!")
    print("Please select an option. Enter the number, thx.")
    print("1. Auto Tagging of everyone")
    print("2. Single tagging of a user")
    user_choice = int(input("Please select an option: "))
    if user_choice == 1:
        dataProcessing.main()
    elif user_choice == 2:
        print ("Current option is still WIP! Check back in the future!")
    else :
        print ("Please select an option. Enter the number, thx.")

# See PyCharm help at https://www.jetbrains.com/help/pycharm/

# This is a sample Python script.
import dataProcessing
import onemapApiHelper

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
    print("3. Geocode all schools")
    user_choice = int(input("Please select an option: "))
    if user_choice == 1:
        dataProcessing.main()
    elif user_choice == 2:
        inputtedtarget = input("Please enter the names of peoples to be swap! (To enter multiple name put a comma in between each name)")
        cleanedinputted = inputtedtarget.split(",")
        massdata_file = "data/final_modeling_assignments_OOP_V2.json"
        token = onemapApiHelper.get_token()
        dataProcessing.targeted_swap(cleanedinputted,massdata_file,token)
    elif user_choice == 3:
        token = onemapApiHelper.get_token()
        school_file_path = "data/schools.xlsx"
        dataProcessing.process_schools(school_file_path, token)
    else :
        print ("Please select an option. Enter the number, thx.")

# See PyCharm help at https://www.jetbrains.com/help/pycharm/

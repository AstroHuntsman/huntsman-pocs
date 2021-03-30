
def get_selection(choices, current=None, prompt='Select new target'):
    """ Given a list of choices, show a menu and prompt the user.

    NOTE THAT THIS ASSUMES RUNNING IN A TERMINALS!
    """
    print()  # Newline
    for i, choice in enumerate(choices):
        selected = '*' if choice == current and current is not None else ' '
        print(f' {selected} [{i}] {choice}', end='')  # No newline
        print()  # Newline

    def get():
        full_prompt = f'\n{prompt}'
        if current:
            full_prompt += f' [{current}]'

        return input(f'{full_prompt}: ')

    while True:
        # Prompt for new index number
        new_idx = get()

        # If default (current)
        if new_idx == '':
            new_choice = current
            print(f'Returning default: {new_choice}')
            break
        else:
            # Make sure a valid selection
            try:
                new_choice = choices[int(new_idx)]
                print(f'New selection: {new_choice}')
                break
            except Exception:
                print("Invalid selection for list, select again or hit Enter for default")
                continue

    return new_choice


def ee():
    # Reading source code is good for you.
    if random.random() >= 0.99:
        print("\n\n")
        print(" 👽 🛸 👽 👽 🛸  👽  🛸 ALIENS!!!! 🛸 👽 🛸  👽  🛸 ")
        print("\n\n")
        print("...just kidding.")
        print("\n")

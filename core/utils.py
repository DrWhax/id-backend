def convert_group_to_select2field_choices(group):
    result = []

    for i in group:
        result.append((i.id, i.profile.display_name))

    return result
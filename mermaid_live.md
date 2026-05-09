erDiagram

    %% ─────────────────────────────────────────
    %% DJANGO AUTH & ADMIN
    %% ─────────────────────────────────────────

    auth_user {
        int id PK
        string username
        string first_name
        string last_name
        string full_name
        string email
        string password
        string profile_picture
        boolean email_verified
        boolean is_superuser
        boolean is_staff
        boolean is_active
        datetime date_joined
        datetime last_login
    }

    auth_group {
        int id PK
        string name
    }

    auth_permission {
        int id PK
        string name
        string codename
        int content_type_id FK
    }

    auth_user_groups {
        int id PK
        int user_id FK
        int group_id FK
    }

    auth_group_permissions {
        int id PK
        int group_id FK
        int permission_id FK
    }

    auth_user_user_permissions {
        int id PK
        int user_id FK
        int permission_id FK
    }

    django_content_type {
        int id PK
        string app_label
        string model
    }

    django_admin_log {
        int id PK
        datetime action_time
        string object_id
        string object_repr
        int action_flag
        text change_message
        int content_type_id FK
        int user_id FK
    }

    django_session {
        string session_key PK
        text session_data
        datetime expire_date
    }

    django_site {
        int id PK
        string domain
        string name
    }

    django_migrations {
        int id PK
        string app
        string name
        datetime applied
    }

    %% ─────────────────────────────────────────
    %% SOCIAL AUTH
    %% ─────────────────────────────────────────

    socialaccount_socialaccount {
        int id PK
        int user_id FK
        string provider
        string uid
        json extra_data
        datetime last_login
        datetime date_joined
    }

    %% ─────────────────────────────────────────
    %% APPLICATION MODELS
    %% ─────────────────────────────────────────

    datasets_dataset {
        int id PK
        int user_id FK
        string file
        string file_name
        string file_format
        bigint file_size
        int parent_id FK
        boolean is_cleaned
        datetime uploaded_date
        datetime updated_date
    }

    issues_issue {
        int id PK
        int dataset_id FK
        string issue_type
        string column_name
        int row_index
        int affected_rows
        text description
        text suggested_fix
        datetime detected_at
    }

    cleaning_cleaningoperation {
        int id PK
        int dataset_id FK
        int issue_id FK
        string operation_type
        string column_name
        json parameters
        int rows_affected
        string status
        datetime applied_at
        datetime created_at
    }

    datasetframe_datasetframe {
        int id PK
        int dataset_id FK
        string model_used
        text result
        datetime created_at
    }

    %% ─────────────────────────────────────────
    %% RELATIONSHIPS — Auth & Admin
    %% ─────────────────────────────────────────

    auth_user ||--o{ auth_user_groups : "belongs to"
    auth_group ||--o{ auth_user_groups : "has member"

    auth_user ||--o{ auth_user_user_permissions : "has"
    auth_permission ||--o{ auth_user_user_permissions : "granted via"

    auth_group ||--o{ auth_group_permissions : "has"
    auth_permission ||--o{ auth_group_permissions : "granted via"

    auth_permission }o--|| django_content_type : "references"

    django_admin_log }o--|| auth_user : "performed by"
    django_admin_log }o--|| django_content_type : "relates to"

    auth_user ||--o{ socialaccount_socialaccount : "linked to"

    %% ─────────────────────────────────────────
    %% RELATIONSHIPS — Application
    %% ─────────────────────────────────────────

    auth_user ||--o{ datasets_dataset : "owns"

    datasets_dataset ||--o{ datasets_dataset : "parent / children"

    datasets_dataset ||--o{ issues_issue : "has issues"

    datasets_dataset ||--o{ cleaning_cleaningoperation : "has cleaning ops"
    issues_issue ||--o{ cleaning_cleaningoperation : "resolved by"

    datasets_dataset ||--o{ datasetframe_datasetframe : "has AI frames"

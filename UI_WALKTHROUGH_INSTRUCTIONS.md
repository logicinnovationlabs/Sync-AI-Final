# Admin Dashboard UI Walkthrough Instructions

## Browser Preview
The admin dashboard is available at: http://localhost:3000

## Required Steps

### 1. Login
- Navigate to http://localhost:3000
- Login with credentials:
  - Email: admin@synq.dev
  - Password: AlphaAdmin123!
  - Tenant: alpha
- **Screenshot:** Login screen and successful login

### 2. Navigate to Member List
- After login, navigate to the admin dashboard
- Go to the member list section
- **Screenshot:** Member list showing document counts

### 3. Verify Document Count
- Note the document count shown for at least one member
- Compare this with a real database query:
  ```sql
  SELECT COUNT(*) FROM canonical_documents WHERE owner_principal_id = '<member_id>';
  ```
- **Screenshot:** Member list with document count visible

### 4. Click "See More" on a Member
- Click "see more" on the member you selected
- Confirm the real document list renders
- **Screenshot:** Document list for the selected member

### 5. Use UI Allow/Deny Control
- Use the actual UI allow/deny control (not the API) to deny one document
- **Screenshot:** UI reflecting the deny change

### 6. Verify Deny Enforcement
- Perform a real search to confirm the deny is enforced
- The denied document should not appear in search results
- **Screenshot:** Search results showing document is absent

### 7. Remove Override via UI
- Use the UI control to remove the override
- **Screenshot:** UI showing the override removal

### 8. Verify Document Reappears
- Perform another search to confirm the document reappears
- **Screenshot:** Search results showing document is back

## Notes
- All screenshots should be taken in the actual browser, not by reading source code
- Each step requires a screenshot to verify completion
- If any step fails, document the failure with a screenshot

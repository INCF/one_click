// one-click deidentification script

- (0008,0050)		// Accession Number
- (0008,0050)         // Accession Number
- (0008,0080)         // InstitutionName
- (0008,0090)         // Referring Physician's Name
- (0008,0096)         // Referring Physician Identification
- (0008,1048)         // Physician(s) of Record
- (0008,1049)         // Physician(s) of Record Identification
- (0008,1050)         // Performing Physicians' Name
- (0008,1052)         // Performing Physician Identification
- (0008,1060)         // Name of Physician(s) Reading Study
- (0008,1062)         // Physician(s) Reading Study Identification
- (0010,0030)         // Patient's Birth Date
- (0010,0050)         // Patient's Insurance Plan Code
- (0010,0101)         // Patient's Primary Language Code
- (0010,1000)         // Other Patient IDs
- (0010,1001)         // Other Patient Names
- (0010,1002)         // Other Patient IDs
- (0010,1005)         // Patient's Birth Name
- (0010,1010)         // Patient's Age
- (0010,1040)         // Patient's Address
- (0010,1060)         // Patient's Mother's Birth Name

(0008,0018) := new UID		// SOP Instance UID
(0020,000D) := new UID		// Study Instance UID
(0020,000E) := new UID		// Series Instance UID
(0020,0052) := new UID		// Frame of Reference UID

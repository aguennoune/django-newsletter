from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext

from django.core.validators import email_re

from django import newforms as forms

from models import *
    
def make_subscription(newsletter, email, name=None):
    if Subscription.objects.filter(newsletter__id=newsletter.id, activated=True, email__exact=email).count():
        #print 'Kappuh nah'
        return None
        
    addr = Subscription(activated=True)
    addr.newsletter = newsletter
    
    addr.email = email
    
    if name:
        addr.name = name
    
    return addr

def parse_csv(myfile, newsletter, ignore_errors=False):
    import csv
    
    myreader = csv.reader(myfile)
    firstrow = myreader.next()

    # Find name column
    colnum = 0
    for column in firstrow:
        if "name" in column.lower() or ugettext("name") in column.lower():
            namecol = colnum

            if "display" in column.lower() or ugettext("display") in column.lower():
                break

        colnum += 1
        
    if not namecol:
        raise forms.ValidationError(_("Name column not found. The name of this column should be either 'name' or '%s'.") % ugettext("name"))
        
    #print 'Name column found \'%s\'' % firstrow[namecol]

    # Find email column
    colnum = 0
    for column in firstrow:
        if 'email' in column.lower() or 'e-mail' in column.lower() or ugettext("e-mail") in column.lower():
            mailcol = colnum

            break

        colnum += 1
        
    if not mailcol:
        raise forms.ValidationError(_("E-mail column not found. The name of this column should be either 'email', 'e-mail' or '%s'.") % ugettext("e-mail"))

    #print 'E-mail column found \'%s\'' % firstrow[mailcol]

    #assert namecol != mailcol, 'Name and e-mail column should not be the same.'
    if namecol == mailcol:
        raise forms.ValidationError(_("Could not properly determine the proper columns in the CSV-file. There should be a field called 'name' or '%s' and one called 'e-mail' or '%s'.") % (_("name"), _("e-mail")))

    print
    print 'Extracting data...'
    
    addresses = {}
    for row in myreader:
        name = row[namecol]
        email = row[mailcol]

        if email_re.search(email):
            addr = make_subscription(newsletter, email, name)
        elif not ignore_errors:
                raise forms.ValidationError(_("Entry '%s' does not contain a valid e-mail address.") % name)
            
        if addr:
            if addresses.has_key(email) and not ignore_errors:
                raise forms.ValidationError(_("The address file contains duplicate entries for '%s'.") % email)

            addresses.update({email:addr})
        elif not ignore_errors:
            raise forms.ValidationError(_("Some entries are already subscribed to."))

    return addresses
        
def parse_vcard(myfile, newsletter, ignore_errors=False):
    from addressimport import vobject
    
    myvcards = vobject.readComponents(myfile)
    
    addresses = {}
    
    for myvcard in myvcards:
        if hasattr(myvcard, 'fn'):
            name = myvcard.fn.value
        else:
            name = None
            
        if hasattr(myvcard, 'email'):
            email = myvcard.email.value
        elif not ignore_errors:
            raise forms.ValidationError(_("Entry '%s' contains no email address.") % name)

        if email_re.search(email):
            addr = make_subscription(newsletter, email, name)
        elif not ignore_errors:
                raise forms.ValidationError(_("Entry '%s' does not contain a valid e-mail address.") % name)

        if addr:
            if addresses.has_key(email) and not ignore_errors:
                raise forms.ValidationError(_("The address file contains duplicate entries for '%s'.") % email)
                
            addresses.update({email:addr})
        elif not ignore_errors:
            raise forms.ValidationError(_("Some entries are already subscribed to."))

    return addresses    

def parse_ldif(myfile, newsletter, ignore_errors=False):
    from addressimport import ldif
    class AddressParser(ldif.LDIFParser):
        addresses = {}

        def handle(self, dn, entry):
            if entry.has_key('mail'):
                email = entry['mail'][0]
                if entry.has_key('cn'):
                    name = entry['cn'][0]
                else:
                    name = None
         
                if email_re.search(email):
                    addr = make_subscription(newsletter, email, name)
                elif not ignore_errors:
                        raise forms.ValidationError(_("Entry '%s' does not contain a valid e-mail address.") % name)

                if addr:
                    if self.addresses.has_key(email) and not ignore_errors:
                        raise forms.ValidationError(_("The address file contains duplicate entries for '%s'.") % email)
                        
                    self.addresses.update({email:addr})
                elif not ignore_errors:
                    raise forms.ValidationError(_("Some entries are already subscribed to."))
                    
            elif not ignore_errors:
                raise forms.ValidationError(_("Some entries have no e-mail address."))
    try:
        myparser = AddressParser(myfile)
        myparser.parse()
    except ValueError, e:
        if ignore_errors:
            raise forms.ValidationError(e.message)    
            
    return myparser.addresses
         
class ImportForm(forms.Form):
    def clean(self):
        # If there are validation errors earlier on, don't bother.
        if not (self.cleaned_data.has_key('address_file') and self.cleaned_data.has_key('ignore_errors') and self.cleaned_data.has_key('newsletter')):
            return self.cleaned_data
            #raise forms.ValidationError(_("No file has been specified."))                
            
        ignore_errors = self.cleaned_data['ignore_errors']
        newsletter = self.cleaned_data['newsletter']
        myfile = self.cleaned_data['address_file']

        myfield = self.base_fields['address_file']
        myvalue = myfield.widget.value_from_datadict(self.data, self.files, self.add_prefix('address_file'))
        
        content_type = myvalue.content_type
        allowed_types = ['text/plain', 'application/octet-stream', ]
        if content_type not in allowed_types:
            raise forms.ValidationError(_("File type '%s' was not recognized.") % content_type)

        self.addresses = []
        
        ext = myvalue.file_name.rsplit('.', 1)[-1].lower()
        if ext == 'vcf':
            self.addresses = parse_vcard(myvalue.file, newsletter, ignore_errors)
            
        elif ext == 'ldif':
            self.addresses = parse_ldif(myvalue.file, newsletter, ignore_errors)

        elif ext == 'csv':
            self.addresses = parse_csv(myvalue.file, newsletter, ignore_errors)
            
        else:
            raise forms.ValidationError(_("File extention '%s' was not recognized.") % ext)

        if len(self.addresses) == 0:
            raise forms.ValidationError(_("No entries could found in this file."))
        #else:
        #    print 'Found addresses', self.addresses
            
        return self.cleaned_data

    def get_addresses(self):
        if hasattr(self, 'addresses'):
            print 'Getting addresses', self.addresses
            return self.addresses
        else:
            return {}
    
    newsletter = forms.ModelChoiceField(label=_("Newsletter"),queryset=Newsletter.objects.all(), initial=Newsletter.get_default_id())    
    address_file = forms.FileField(label=_("Address file"))
    ignore_errors = forms.BooleanField(label=_("Ignore non-fatal errors"), initial=False, required=False)
    
class ConfirmForm(forms.Form):
    def clean(self):
        value = self.cleaned_data['confirm']
        
        if not value:
            raise forms.ValidationError(_("You should confirm in order to continue."))
        
    confirm = forms.BooleanField(label=_("Confirm import"),initial=True, widget=forms.HiddenInput)
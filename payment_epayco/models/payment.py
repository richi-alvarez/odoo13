# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib

from werkzeug import urls

from odoo import api, fields, models, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.tools.float_utils import float_compare

import logging

_logger = logging.getLogger(__name__)


class PaymentAcquirerEpayco(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('epayco', 'Epayco')])
    epayco_merchant_id = fields.Char(string='P_CUST_ID', required_if_provider='epayco', groups='base.group_user')
    epayco_merchant_key = fields.Char(string='PUBLICK_KEY', required_if_provider='epayco', groups='base.group_user')
    epayco_p_key = fields.Char(string='P_KEY', required_if_provider='epayco', groups='base.group_user')

    def epayco_form_generate_values(self, values):
        self.ensure_one()
        environment = 'false' if self.state == 'enabled' else 'true'
        country = values.get('partner_country').code.lower(),
        base_url = self.get_base_url()
        url_response = urls.url_join(base_url, '/payment/epayco/response/')
        confirmation_url = urls.url_join(base_url, '/payment/epayco/confirmation/')
        epayco_values = dict(values,
                                public_key=self.epayco_merchant_key,
                                txnid=values['reference'],
                                amount=values['amount'],
                                productinfo=values['reference'],
                                firstname=values.get('partner_name'),
                                email=values.get('partner_email'),
                                phone=values.get('partner_phone'),
                                currency_code=values['currency'].code.lower(),
                                country_code=country,
                                epayco_checkout_external="true",
                                epayco_env_test=environment,
                                epayco_lang="es",
                                response_url=url_response,
                                confirmation_url=confirmation_url
                                )
        return epayco_values

    def epayco_get_form_action_url(self):
        self.ensure_one()
        return '/payment/epayco/checkout/'


    def _epayco_generate_sign(self, values):
        """ Generate the shasign for incoming or outgoing communications.
        :param self: the self browse record. It should have a shakey in shakey out
        :param string inout: 'in' (odoo contacting epayco) or 'out' (epayco
                             contacting odoo).
        :param dict values: transaction values

        :return string: shasign
        """
        self.ensure_one()
        p_cust_id_client = self.epayco_merchant_id
        p_key = self.epayco_p_key
        x_ref_payco = values.get('x_ref_payco')
        x_transaction_id = values.get('x_transaction_id')
        x_amount = values.get('x_amount')
        x_currency_code = values.get('x_currency_code')
        hash_str_bytes = bytes('%s^%s^%s^%s^%s^%s' % (
            p_cust_id_cliente,
            p_key,
            x_ref_payco,
            x_transaction_id,
            x_amount,
            x_currency_code), 'utf-8')
        hash_object = hashlib.sha256(hash_str_bytes)
        hash = hash_object.hexdigest()
        return hash


class PaymentTransactionEpayco(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _epayco_form_get_tx_from_data(self, data):
        """ Given a data dict coming from epayco, verify it and find the related
        transaction record. """
        reference = data.get('x_extra1')
        signature = data.get('x_signature')
        if not reference or not pay_id or not shasign:
            raise ValidationError(_('Epayco: received data with missing reference (%s) or signature (%s)') % (reference, signature))

        transaction = self.search([('reference', '=', reference)])

        if not transaction:
            error_msg = (_('Epayco: received data for reference %s; no order found') % (reference))
            raise ValidationError(error_msg)
        elif len(transaction) > 1:
            error_msg = (_('Epayco: received data for reference %s; multiple orders found') % (reference))
            raise ValidationError(error_msg)

        #verify signature
        reference = data.get('x_extra1')
        signature = data.get('x_signature')
        shasign_check = transaction.acquirer_id._epayco_generate_sign(data)
        if shasign_check != signature:
            raise ValidationError(_('Epayco: invalid signature, received %s, computed %s, for data %s') % (signature, shasign_check, data))
        return transaction

    def _epayco_form_get_invalid_parameters(self, data):
        invalid_parameters = []

        if self.acquirer_reference and data.get('x_transaction_id') != self.acquirer_reference:
            invalid_parameters.append(
                ('Transaction Id', data.get('x_transaction_id'), self.acquirer_reference))
        #check what is buyed
        if int(self.acquirer_id.epayco_merchant_id) != int(data.get         ('x_cust_id_cliente')):
            invalid_parameters.append(
                ('Customer ID', data.get('x_cust_id_cliente'), self.acquirer_id.epayco_merchant_id))

        return invalid_parameters

    def _epayco_form_validate(self, data):
        status = data.get('x_transaction_state')
        result = self.write({
            'acquirer_reference': data.get('x_ref_payco'),
            'date': fields.Datetime.now(),
        })
        if status == 'Aceptada':
            self._set_transaction_done()
        elif status == 'Pendiente':
            self._set_transaction_pending()
        else:
            self._set_transaction_cancel()
        return result
